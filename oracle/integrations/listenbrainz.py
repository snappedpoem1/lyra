"""ListenBrainz community top-track scout.

Pulls global listening data for artists in the connection graph and seeds
acquisition_queue with tracks the broader community considers essential —
not just what you personally played on Spotify.

No API key required. All endpoints are public and rate-limited to ~1 req/sec.

API: https://listenbrainz.readthedocs.io/en/latest/users/api/popularity.html

Endpoints used:
    GET /1/popularity/top-recordings-for-artist/{artist_mbid}?count=10

Flow:
    1. Pull external connection targets (not in library), sorted by edge weight.
    2. Also pull your own top library artists by taste alignment.
    3. Resolve each artist name → MusicBrainz MBID (cached via existing Lore infra).
    4. Call ListenBrainz for their globally top-listened recordings.
    5. Filter out tracks already in library or already in acquisition_queue.
    6. Insert with source='listenbrainz_community' and priority_score derived
       from edge weight × listen popularity.

Usage::

    from oracle.integrations.listenbrainz import discover_community_tracks
    added = discover_community_tracks(limit_artists=60, tracks_per_artist=8)
    print(f"Added {added} community-sourced candidates to acquisition queue")
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set, Tuple

import requests

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

_LB_BASE = "https://api.listenbrainz.org/1"
_MB_BASE = "https://musicbrainz.org/ws/2"
_RATE_LIMIT_SECONDS = 1.1          # ListenBrainz: generous limit
_MB_RATE_LIMIT_SECONDS = 1.2       # MusicBrainz: 1 req/sec
_REQUEST_TIMEOUT = 12
_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7   # 7 days


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "LyraOracle/9.0 (github.com/snappedpoem1/lyra)",
        "Accept": "application/json",
    })
    return s


# ---------------------------------------------------------------------------
# MusicBrainz MBID resolution (cached via enrich_cache)
# ---------------------------------------------------------------------------

_last_mb_req: float = 0.0


def _mb_rate_limit() -> None:
    global _last_mb_req
    elapsed = time.time() - _last_mb_req
    if elapsed < _MB_RATE_LIMIT_SECONDS:
        time.sleep(_MB_RATE_LIMIT_SECONDS - elapsed)
    _last_mb_req = time.time()


def _get_mbid(artist_name: str, sess: requests.Session) -> Optional[str]:
    """Resolve artist name → MusicBrainz MBID, cached in enrich_cache."""
    cache_key = f"mbid:{artist_name.lower().strip()}"
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT payload_json FROM enrich_cache "
            "WHERE provider = 'listenbrainz_mbid' AND lookup_key = ? "
            "AND fetched_at > ?",
            (cache_key, time.time() - _CACHE_TTL_SECONDS),
        )
        row = c.fetchone()
        if row:
            import json as _json
            payload = _json.loads(row[0])
            return payload.get("mbid")
    finally:
        conn.close()

    # Not cached — query MusicBrainz
    _mb_rate_limit()
    try:
        resp = sess.get(
            f"{_MB_BASE}/artist",
            params={"query": f"artist:{artist_name}", "fmt": "json", "limit": 1},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        artists = data.get("artists", [])
        mbid = artists[0].get("id") if artists else None
    except Exception as exc:
        logger.debug("[listenbrainz] MBID lookup failed for '%s': %s", artist_name, exc)
        return None

    # Cache the result (even None = cache miss marker to avoid repeat hits)
    import json as _json
    conn2 = get_connection()
    try:
        c2 = conn2.cursor()
        c2.execute(
            "INSERT OR REPLACE INTO enrich_cache "
            "(provider, lookup_key, payload_json, fetched_at) VALUES (?, ?, ?, ?)",
            ("listenbrainz_mbid", cache_key, _json.dumps({"mbid": mbid}), time.time()),
        )
        conn2.commit()
    finally:
        conn2.close()

    return mbid


# ---------------------------------------------------------------------------
# ListenBrainz top recordings
# ---------------------------------------------------------------------------

_last_lb_req: float = 0.0


def _lb_rate_limit() -> None:
    global _last_lb_req
    elapsed = time.time() - _last_lb_req
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_lb_req = time.time()


def _get_top_recordings(
    artist_mbid: str,
    artist_name: str,
    count: int,
    sess: requests.Session,
) -> List[Dict]:
    """Fetch community top recordings from ListenBrainz for an artist MBID.

    Returns list of dicts with 'artist', 'title', 'listen_count'.
    """
    cache_key = f"top_rec:{artist_mbid}:{count}"
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT payload_json FROM enrich_cache "
            "WHERE provider = 'listenbrainz_top' AND lookup_key = ? "
            "AND fetched_at > ?",
            (cache_key, time.time() - _CACHE_TTL_SECONDS),
        )
        row = c.fetchone()
        if row:
            import json as _json
            return _json.loads(row[0]).get("recordings", [])
    finally:
        conn.close()

    _lb_rate_limit()
    try:
        resp = sess.get(
            f"{_LB_BASE}/popularity/top-recordings-for-artist/{artist_mbid}",
            params={"count": count},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.debug("[listenbrainz] top-recordings returned %d for %s", resp.status_code, artist_name)
            return []
        data = resp.json()
        raw = data.get("recordings", [])
    except Exception as exc:
        logger.debug("[listenbrainz] top-recordings request failed for '%s': %s", artist_name, exc)
        return []

    recordings = [
        {
            "artist": r.get("artist_name", artist_name),
            "title": r.get("recording_name", ""),
            "listen_count": int(r.get("total_listen_count", 0)),
            "recording_mbid": r.get("recording_mbid", ""),
        }
        for r in raw
        if r.get("recording_name")
    ]

    import json as _json
    conn2 = get_connection()
    try:
        c2 = conn2.cursor()
        c2.execute(
            "INSERT OR REPLACE INTO enrich_cache "
            "(provider, lookup_key, payload_json, fetched_at) VALUES (?, ?, ?, ?)",
            ("listenbrainz_top", cache_key, _json.dumps({"recordings": recordings}), time.time()),
        )
        conn2.commit()
    finally:
        conn2.close()

    return recordings


# ---------------------------------------------------------------------------
# Library / queue helpers
# ---------------------------------------------------------------------------

def _load_library_set(conn) -> Set[str]:
    """Return a set of 'lower(artist)|lower(title)' for all active tracks."""
    c = conn.cursor()
    c.execute("SELECT LOWER(artist), LOWER(title) FROM tracks WHERE status = 'active'")
    return {f"{r[0]}|{r[1]}" for r in c.fetchall()}


def _load_queue_set(conn) -> Set[str]:
    """Return a set of 'lower(artist)|lower(title)' for all pending/queued items."""
    c = conn.cursor()
    c.execute(
        "SELECT LOWER(artist), LOWER(title) FROM acquisition_queue "
        "WHERE status IN ('pending', 'queued')",
    )
    return {f"{r[0]}|{r[1]}" for r in c.fetchall()}


def _insert_queue_items(conn, items: List[Dict]) -> int:
    """Bulk-insert acquisition_queue rows. Returns count of rows inserted."""
    if not items:
        return 0
    c = conn.cursor()
    inserted = 0
    for item in items:
        try:
            c.execute(
                """
                INSERT INTO acquisition_queue
                    (artist, title, priority_score, source, search_query, status)
                SELECT ?, ?, ?, ?, ?, 'pending'
                WHERE NOT EXISTS (
                    SELECT 1 FROM acquisition_queue
                    WHERE LOWER(artist) = LOWER(?) AND LOWER(title) = LOWER(?)
                    AND status != 'completed'
                )
                """,
                (
                    item["artist"],
                    item["title"],
                    item["priority_score"],
                    "listenbrainz_community",
                    f"{item['artist']} {item['title']}",
                    item["artist"],
                    item["title"],
                ),
            )
            inserted += c.rowcount
        except Exception as exc:
            logger.debug("[listenbrainz] insert failed for %s / %s: %s", item["artist"], item["title"], exc)
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Target artist selection
# ---------------------------------------------------------------------------

def _get_external_connection_targets(conn, limit: int) -> List[Tuple[str, float]]:
    """External connection targets (not in library), sorted by total edge weight."""
    c = conn.cursor()
    c.execute(
        """
        SELECT c.target, SUM(c.weight) AS total_weight
        FROM connections c
        WHERE NOT EXISTS (
            SELECT 1 FROM tracks t
            WHERE LOWER(t.artist) = LOWER(c.target) AND t.status = 'active'
        )
        GROUP BY c.target
        ORDER BY total_weight DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [(r[0], float(r[1])) for r in c.fetchall()]


def _get_top_library_artists(conn, limit: int) -> List[Tuple[str, float]]:
    """Top library artists by taste alignment (taste_profile match) and play count."""
    c = conn.cursor()
    c.execute(
        """
        SELECT t.artist, COUNT(*) AS track_count
        FROM tracks t
        WHERE t.status = 'active'
          AND t.artist IS NOT NULL AND trim(t.artist) != ''
        GROUP BY t.artist
        ORDER BY track_count DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [(r[0], float(r[1])) for r in c.fetchall()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_community_tracks(
    limit_artists: int = 60,
    tracks_per_artist: int = 8,
    include_library_artists: bool = True,
    min_listen_count: int = 50,
) -> int:
    """Discover community-sourced tracks via ListenBrainz and queue them for acquisition.

    Combines two artist pools:
    - External graph connection targets (artists connected but not in library)
    - Your own top library artists (what do their peers consider essential?)

    Args:
        limit_artists: Max total artists to query across both pools (split 60/40).
        tracks_per_artist: Community top recordings to fetch per artist.
        include_library_artists: Also scout your own top library artists.
        min_listen_count: Minimum global listen count to consider a recording.

    Returns:
        Number of new items added to acquisition_queue.
    """
    external_limit = limit_artists if not include_library_artists else (limit_artists * 3 // 5)
    library_limit = limit_artists - external_limit

    sess = _session()
    total_added = 0

    conn = get_connection()
    try:
        lib_set = _load_library_set(conn)
        queue_set = _load_queue_set(conn)

        external_artists = _get_external_connection_targets(conn, limit=external_limit)
        library_artists = _get_top_library_artists(conn, limit=library_limit) if include_library_artists else []
    finally:
        conn.close()

    # Combine, deduplicate, external first (highest discovery value)
    seen_artists: Set[str] = set()
    artist_pool: List[Tuple[str, float]] = []
    for name, weight in external_artists + library_artists:
        key = name.lower().strip()
        if key and key not in seen_artists:
            seen_artists.add(key)
            artist_pool.append((name, weight))

    logger.info(
        "[listenbrainz] scouting %d artists (%d external / %d library)",
        len(artist_pool), len(external_artists), len(library_artists),
    )

    # Normalise weight to 0–10 priority range
    max_weight = max((w for _, w in artist_pool), default=1.0)

    queue_items: List[Dict] = []

    for artist_name, weight in artist_pool:
        mbid = _get_mbid(artist_name, sess)
        if not mbid:
            logger.debug("[listenbrainz] no MBID for '%s' — skipping", artist_name)
            continue

        recordings = _get_top_recordings(mbid, artist_name, count=tracks_per_artist, sess=sess)

        for rec in recordings:
            title = rec.get("title", "").strip()
            rec_artist = rec.get("artist", artist_name).strip()
            listen_count = rec.get("listen_count", 0)

            if not title or listen_count < min_listen_count:
                continue

            key = f"{rec_artist.lower()}|{title.lower()}"
            if key in lib_set or key in queue_set:
                continue

            # Priority: weight from graph edge × listen popularity signal (log-scaled)
            import math
            pop_boost = min(1.0, math.log10(max(10, listen_count)) / 6.0)  # 0–1
            edge_factor = (weight / max_weight) if max_weight > 0 else 0.5
            priority = round(5.0 + 3.5 * edge_factor + 1.5 * pop_boost, 2)

            queue_items.append({
                "artist": rec_artist,
                "title": title,
                "priority_score": priority,
            })
            queue_set.add(key)  # prevent duplicates within this run

    if queue_items:
        conn2 = get_connection()
        try:
            total_added = _insert_queue_items(conn2, queue_items)
        finally:
            conn2.close()

    logger.info(
        "[listenbrainz] done — %d candidates queued from %d artists",
        total_added, len(artist_pool),
    )
    return total_added
