"""Last.fm listening history sync — passive playback telemetry from any source.

Pulls a user's Last.fm recent tracks via pylast and converts them to Lyra
taste signals. This captures every play the user scrobbles regardless of
which app they listened in — Spotify, phone, desktop, anything.

Env vars:
    LASTFM_API_KEY      — Last.fm API key (required)
    LASTFM_API_SECRET   — Last.fm API secret (required)
    LASTFM_USERNAME     — Last.fm username to sync (required)

Usage:
    from oracle.integrations.lastfm_history import sync_lastfm_to_taste
    stats = sync_lastfm_to_taste(lookback_days=30)

Called by worker.py on a 30-minute schedule.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")
_LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET", "")
_LASTFM_USERNAME = os.getenv("LASTFM_USERNAME", "")
_MIN_MS_PLAYED = 30_000  # treat as intentional play if >30s (approx)


# ---------------------------------------------------------------------------
# Cursor building (reuse taste_backfill index helpers)
# ---------------------------------------------------------------------------

def _resolve_track_id(cursor, artist: str, title: str) -> Optional[str]:
    """Resolve artist+title to local track_id — mirrors taste_backfill logic."""
    from oracle.taste_backfill import _TRACK_INDEX, _norm

    a_norm = _norm(artist)
    t_norm = _norm(title)

    # Pass 0: exact normalized
    for track_id, db_artist, db_title in _TRACK_INDEX:
        if db_artist == a_norm and db_title == t_norm:
            return track_id

    # Pass 1: rapidfuzz
    try:
        from rapidfuzz import fuzz, process as rf_process  # type: ignore

        query_key = f"{a_norm} {t_norm}"
        candidates = [(tid, f"{da} {dt}") for tid, da, dt in _TRACK_INDEX]
        if candidates:
            keys = [c[1] for c in candidates]
            result = rf_process.extractOne(
                query_key, keys, scorer=fuzz.WRatio, score_cutoff=85
            )
            if result is not None:
                _, _score, idx = result
                return candidates[idx][0]
    except ImportError:
        pass

    return None


def _ensure_track_index_populated(cursor) -> None:
    """Ensure taste_backfill._TRACK_INDEX is populated before resolution."""
    from oracle.taste_backfill import _TRACK_INDEX, _build_track_index

    if not _TRACK_INDEX:
        _build_track_index(cursor)


# ---------------------------------------------------------------------------
# Last.fm pull
# ---------------------------------------------------------------------------

def _get_lastfm_plays(
    username: str,
    api_key: str,
    api_secret: str,
    since_ts: int,
) -> List[Tuple[str, str, int]]:
    """Pull recent tracks from Last.fm since unix timestamp.

    Returns list of (artist, title, unix_ts) tuples, newest first.
    """
    try:
        import pylast  # type: ignore
    except ImportError:
        logger.error("[lastfm] pylast not installed — run: pip install pylast")
        return []

    try:
        network = pylast.LastFMNetwork(
            api_key=api_key,
            api_secret=api_secret,
        )
        user = network.get_user(username)
        # pylast.PERIOD_* not useful here — use time_from parameter
        recent = user.get_recent_tracks(limit=None, time_from=since_ts)
    except Exception as exc:
        logger.error("[lastfm] failed to fetch recent tracks: %s", exc)
        return []

    plays: List[Tuple[str, str, int]] = []
    for played in recent:
        try:
            track = played.track
            artist = track.artist.name if track.artist else ""
            title = track.title or ""
            ts = int(played.timestamp) if played.timestamp else int(time.time())
            if artist and title:
                plays.append((artist, title, ts))
        except Exception:
            continue

    logger.info("[lastfm] fetched %d plays since %s", len(plays), datetime.utcfromtimestamp(since_ts).isoformat())
    return plays


# ---------------------------------------------------------------------------
# Sync entry point
# ---------------------------------------------------------------------------

def sync_lastfm_to_taste(
    lookback_days: int = 7,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Pull Last.fm history and push signals into taste_profile.

    Args:
        lookback_days: How many days back to pull. Default 7 (incremental).
        dry_run: Resolve and compute but don't write.

    Returns:
        Stats dict: fetched, matched, unmatched, written, taste_errors.
    """
    api_key = _LASTFM_API_KEY
    api_secret = _LASTFM_API_SECRET
    username = _LASTFM_USERNAME

    if not all([api_key, api_secret, username]):
        logger.warning(
            "[lastfm] LASTFM_API_KEY, LASTFM_API_SECRET, LASTFM_USERNAME must all be set"
        )
        return {"skipped": True, "reason": "missing_credentials"}

    since_ts = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp())

    plays = _get_lastfm_plays(username, api_key, api_secret, since_ts)
    if not plays:
        return {"fetched": 0, "matched": 0, "unmatched": 0, "written": 0}

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    _ensure_track_index_populated(cursor)

    # Group plays by (artist, title) → count
    from collections import defaultdict
    play_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for artist, title, _ts in plays:
        play_counts[(artist, title)] += 1

    matched = 0
    unmatched = 0
    details = []

    for (artist, title), count in play_counts.items():
        track_id = _resolve_track_id(cursor, artist, title)
        if not track_id:
            unmatched += 1
            continue
        matched += 1
        # Last.fm plays are not explicitly skipped — treat as all positive signals
        weight = min(math.log2(count + 1), 3.0)
        details.append((track_id, True, weight))

    conn.close()

    if dry_run:
        logger.info("[lastfm] DRY RUN — %d matched, %d unmatched", matched, unmatched)
        return {"dry_run": True, "fetched": len(plays), "matched": matched, "unmatched": unmatched}

    if get_write_mode() != "apply_allowed":
        logger.warning("[lastfm] write blocked (mode=%s)", get_write_mode())
        return {"skipped": True, "reason": "write_blocked", "matched": matched}

    from oracle.taste import update_taste_from_playback

    written = 0
    taste_errors = 0
    for track_id, positive, weight in details:
        result = update_taste_from_playback(track_id, positive=positive, weight=weight)
        if result.get("updated", 0) > 0:
            written += 1
        else:
            taste_errors += 1

    logger.info(
        "[lastfm] sync complete: fetched=%d matched=%d written=%d errors=%d",
        len(plays), matched, written, taste_errors,
    )
    return {
        "fetched": len(plays),
        "matched": matched,
        "unmatched": unmatched,
        "written": written,
        "taste_errors": taste_errors,
    }
