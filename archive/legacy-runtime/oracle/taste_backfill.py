"""Taste backfill from Spotify extended streaming history.

Bridges the gap between spotify_history (127K+ records of real listening)
and the taste_profile table. Groups plays by track, resolves to local
track_ids, and feeds aggregated signals to update_taste_from_playback.

Resolution uses a two-pass strategy for maximum match coverage:
  Pass 0: Normalized exact match (lowercase, stripped punctuation)
  Pass 1: rapidfuzz WRatio >= 85 against full active track index

Usage:
    from oracle.taste_backfill import backfill_taste_from_spotify_history
    stats = backfill_taste_from_spotify_history(dry_run=True)

CLI:
    oracle taste backfill [--min-ms 30000] [--dry-run]
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Track index cache — populated once per backfill run, reused for all lookups
# ---------------------------------------------------------------------------
_TRACK_INDEX: List[Tuple[str, str, str]] = []  # (track_id, artist_norm, title_norm)


def _norm(s: str) -> str:
    """Lowercase, strip punctuation/featured credits for matching."""
    s = s.lower()
    # strip featured artists: "feat.", "ft.", "with ", parenthetical
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)
    s = re.sub(r"\s*feat\.?\s.*", "", s)
    s = re.sub(r"\s*ft\.?\s.*", "", s)
    # strip non-alphanumeric except spaces
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _build_track_index(cursor) -> None:
    """Load all active tracks into module-level index for rapidfuzz."""
    global _TRACK_INDEX
    cursor.execute(
        "SELECT track_id, artist, title FROM tracks WHERE status = 'active'"
    )
    _TRACK_INDEX = [
        (row[0], _norm(row[1] or ""), _norm(row[2] or ""))
        for row in cursor.fetchall()
    ]
    logger.info("[backfill] track index loaded: %d entries", len(_TRACK_INDEX))


def _resolve_track_id(
    cursor, artist: str, title: str
) -> Optional[str]:
    """Resolve artist+title to track_id using two-pass strategy.

    Pass 0: Exact normalized match — fast dict lookup, zero false positives.
    Pass 1: rapidfuzz WRatio >= 85 over artist AND title — catches punctuation
            differences, parenthetical variants, and typos.
    Falls back to LIKE if the index is empty (cold path).
    """
    a_norm = _norm(artist)
    t_norm = _norm(title)

    # Pass 0: exact normalized match
    for track_id, db_artist, db_title in _TRACK_INDEX:
        if db_artist == a_norm and db_title == t_norm:
            return track_id

    # Pass 1: rapidfuzz fuzzy match
    try:
        from rapidfuzz import fuzz, process as rf_process  # type: ignore

        # Build combined key for joint scoring (artist ++ title)
        query_key = f"{a_norm} {t_norm}"
        candidates = [
            (tid, f"{da} {dt}")
            for tid, da, dt in _TRACK_INDEX
        ]
        if candidates:
            keys = [c[1] for c in candidates]
            result = rf_process.extractOne(
                query_key, keys, scorer=fuzz.WRatio, score_cutoff=85
            )
            if result is not None:
                _, score, idx = result
                return candidates[idx][0]
    except ImportError:
        pass  # rapidfuzz not installed; fall through to LIKE

    # LIKE fallback (cold path — no index built)
    cursor.execute(
        "SELECT track_id FROM tracks "
        "WHERE LOWER(artist) LIKE LOWER(?) AND LOWER(title) LIKE LOWER(?) "
        "AND status = 'active' LIMIT 1",
        (f"%{artist}%", f"%{title}%"),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def backfill_taste_from_spotify_history(
    min_ms_played: int = 30000,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill taste_profile from Spotify extended streaming history.

    Groups spotify_history by (artist, track), resolves each to a local
    track_id, determines positive/negative signal from play vs skip ratio,
    and calls update_taste_from_playback with aggregated weight.

    Args:
        min_ms_played: Minimum average ms_played per stream to count as a
            real play (filters out accidental taps). Default 30s.
        dry_run: If True, resolve and compute signals but don't write.

    Returns:
        Stats dict with matched, unmatched, positive, negative counts.
    """
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    # Build in-memory track index for rapidfuzz resolution
    _build_track_index(cursor)

    # Step 1: Aggregate spotify_history by (artist, track)
    logger.info("[backfill] Aggregating Spotify history...")
    cursor.execute("""
        SELECT
            artist,
            track,
            COUNT(*) AS play_count,
            SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) AS skip_count,
            SUM(ms_played) AS total_ms,
            MAX(played_at) AS last_played
        FROM spotify_history
        WHERE artist IS NOT NULL AND artist != ''
          AND track IS NOT NULL AND track != ''
        GROUP BY LOWER(artist), LOWER(track)
        ORDER BY play_count DESC
    """)
    groups = cursor.fetchall()
    logger.info("[backfill] %d unique artist+track groups from history", len(groups))

    # Step 2: Resolve each to track_id and compute signal
    matched = 0
    unmatched = 0
    positive_count = 0
    negative_count = 0
    skipped_write_blocked = 0
    details: List[Dict[str, Any]] = []

    for artist, track, play_count, skip_count, total_ms, last_played in groups:
        track_id = _resolve_track_id(cursor, artist, track)
        if not track_id:
            unmatched += 1
            continue

        matched += 1
        non_skip_count = play_count - skip_count
        avg_ms = total_ms / play_count if play_count > 0 else 0

        # Determine positive/negative signal
        positive = non_skip_count > skip_count and avg_ms >= min_ms_played
        weight = min(math.log2(play_count + 1), 3.0)

        details.append({
            "artist": artist,
            "track": track,
            "track_id": track_id,
            "play_count": play_count,
            "skip_count": skip_count,
            "avg_ms": round(avg_ms),
            "positive": positive,
            "weight": round(weight, 2),
        })

        if positive:
            positive_count += 1
        else:
            negative_count += 1

    conn.close()

    logger.info(
        "[backfill] Resolved %d tracks (%d positive, %d negative), %d unmatched",
        matched, positive_count, negative_count, unmatched,
    )

    if dry_run:
        logger.info("[backfill] DRY RUN — no writes performed")
        # Show top 10 matches
        for d in details[:10]:
            signal = "+" if d["positive"] else "-"
            logger.info(
                "  [%s] %s - %s  (plays=%d, skips=%d, weight=%.2f)",
                signal, d["artist"], d["track"],
                d["play_count"], d["skip_count"], d["weight"],
            )
        return {
            "dry_run": True,
            "matched": matched,
            "unmatched": unmatched,
            "positive": positive_count,
            "negative": negative_count,
            "sample": details[:20],
        }

    # Step 3: Write signals
    if get_write_mode() != "apply_allowed":
        logger.warning(
            "[backfill] Write mode is '%s', not 'apply_allowed'. "
            "Set LYRA_WRITE_MODE=apply_allowed to proceed.",
            get_write_mode(),
        )
        return {
            "matched": matched,
            "unmatched": unmatched,
            "positive": positive_count,
            "negative": negative_count,
            "written": 0,
            "reason": "write_blocked",
        }

    from oracle.taste import update_taste_from_playback

    written = 0
    taste_errors = 0
    history_rows: list = []

    # Phase 1: Update taste profile (each call opens/closes its own connection)
    for i, d in enumerate(details):
        result = update_taste_from_playback(
            d["track_id"], positive=d["positive"], weight=d["weight"]
        )
        if result.get("updated", 0) > 0:
            written += 1
            completion = 1.0 if d["positive"] else 0.2
            history_rows.append((
                d["track_id"], time.time(), 0 if d["positive"] else 1, completion,
            ))
        else:
            taste_errors += 1

        if (i + 1) % 200 == 0:
            logger.info("[backfill] %d/%d taste updates...", i + 1, len(details))

    # Phase 2: Batch-insert playback_history rows (single connection, no contention)
    if history_rows:
        history_conn = get_connection(timeout=10.0)
        for row in history_rows:
            try:
                history_conn.execute(
                    """INSERT OR IGNORE INTO playback_history
                       (track_id, ts, context, skipped, completion_rate)
                       VALUES (?, ?, 'spotify_backfill', ?, ?)""",
                    row,
                )
            except Exception as exc:
                logger.debug("[backfill] playback_history insert failed: %s", exc)
        history_conn.commit()
        history_conn.close()

    logger.info(
        "[backfill] Complete: %d taste updates written, %d errors, %d unmatched",
        written, taste_errors, unmatched,
    )

    return {
        "matched": matched,
        "unmatched": unmatched,
        "positive": positive_count,
        "negative": negative_count,
        "written": written,
        "taste_errors": taste_errors,
    }
