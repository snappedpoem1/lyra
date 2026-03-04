"""Taste profile learning.

Priority 6A: update taste_profile based on playback behavior.

This uses track-level dimension scores (track_scores) to learn user preferences.
The taste_profile table stores per-dimension preference value in [-1, 1] and a
confidence in [0, 1].

Update rule (v1): exponential moving average toward (or away from) the played
track's dimension vector.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)

DIMENSIONS = [
    "energy", "valence", "tension", "density", "warmth",
    "movement", "space", "rawness", "complexity", "nostalgia",
]

# Confidence assigned to library-derived seed values.  Lower than real playback
# so any actual listen/skip will quickly override it.
_SEED_CONFIDENCE = 0.25

# Higher confidence for Spotify-derived profile (637K real plays > library AVG).
_SPOTIFY_SEED_CONFIDENCE = 0.55


def seed_taste_from_spotify(overwrite_existing: bool = False) -> Dict[str, Any]:
    """Derive taste profile from Spotify listening history cross-referenced
    with CLAP dimension scores on acquired tracks.

    This is the proper bootstrap: use 637K real listening events to weight
    dimension scores by actual listening time.  Tracks listened to longer
    and more often pull the taste vector harder.

    Algorithm:
        1. Group spotify_history by (artist, track), sum ms_played
        2. Fuzzy-match each to local tracks table
        3. Look up track_scores for matched tracks
        4. Compute listening-time-weighted mean per dimension
        5. Store in taste_profile with confidence 0.55

    Returns:
        Dict with seeded, skipped, matched, unmatched counts.
    """
    conn = get_connection(timeout=30.0)
    try:
        c = conn.cursor()

        # Step 1: Aggregate Spotify listening — total ms per track
        c.execute("""
            SELECT artist, track, SUM(ms_played) as total_ms, COUNT(*) as play_count
            FROM spotify_history
            WHERE ms_played > 30000
            GROUP BY artist, track
            ORDER BY total_ms DESC
        """)
        spotify_agg = c.fetchall()
        if not spotify_agg:
            return {"seeded": [], "skipped": [], "matched": 0, "unmatched": 0,
                    "reason": "no_spotify_history"}

        # Step 2: Build local track index for matching
        c.execute("""
            SELECT t.track_id, LOWER(t.artist), LOWER(t.title),
                   ts.energy, ts.valence, ts.tension, ts.density, ts.warmth,
                   ts.movement, ts.space, ts.rawness, ts.complexity, ts.nostalgia
            FROM tracks t
            JOIN track_scores ts ON t.track_id = ts.track_id
            WHERE t.status = 'active'
        """)
        local_tracks = c.fetchall()
        # Index by (lowercase_artist_fragment, lowercase_title_fragment)
        local_index: Dict[str, tuple] = {}
        for row in local_tracks:
            key = (row[1].strip(), row[2].strip())
            local_index[key] = row

        # Step 3: Match spotify tracks to local scored tracks, accumulate
        dim_weighted_sum: Dict[str, float] = {d: 0.0 for d in DIMENSIONS}
        total_weight = 0.0
        matched = 0
        unmatched = 0

        for sp_artist, sp_track, total_ms, play_count in spotify_agg:
            sp_a = (sp_artist or "").strip().lower()
            sp_t = (sp_track or "").strip().lower()
            if not sp_a or not sp_t:
                continue

            # Try exact match first
            local_row = local_index.get((sp_a, sp_t))

            # Try fuzzy: artist contains or title contains
            if local_row is None:
                for (la, lt), row in local_index.items():
                    if (sp_a in la or la in sp_a) and (sp_t in lt or lt in sp_t):
                        local_row = row
                        break

            if local_row is None:
                unmatched += 1
                continue

            matched += 1
            # Weight = log(ms_played) so heavy rotation tracks don't dominate completely
            import math
            weight = math.log1p(total_ms / 60000.0)  # log(1 + minutes)

            scores = local_row[3:]  # energy through nostalgia
            for i, dim in enumerate(DIMENSIONS):
                if scores[i] is not None:
                    dim_weighted_sum[dim] += float(scores[i]) * weight
            total_weight += weight

        if total_weight == 0 or matched == 0:
            return {"seeded": [], "skipped": [], "matched": matched,
                    "unmatched": unmatched, "reason": "no_matches_with_scores"}

        # Step 4: Compute weighted mean per dimension
        averages: Dict[str, float] = {}
        for dim in DIMENSIONS:
            raw_mean = dim_weighted_sum[dim] / total_weight  # 0..1 space
            averages[dim] = _to_pref(raw_mean)  # convert to -1..1

        if get_write_mode() != "apply_allowed":
            return {"seeded": [], "skipped": list(averages.keys()),
                    "matched": matched, "unmatched": unmatched,
                    "reason": "write_blocked"}

        # Step 5: Store with higher confidence than library seed
        seeded: List[str] = []
        skipped: List[str] = []

        for dim, val in averages.items():
            if not overwrite_existing:
                c.execute("SELECT confidence FROM taste_profile WHERE dimension = ?", (dim,))
                existing = c.fetchone()
                if existing and float(existing[0]) >= 0.7:
                    skipped.append(dim)
                    continue

            c.execute(
                "INSERT OR REPLACE INTO taste_profile (dimension, value, confidence, last_updated) "
                "VALUES (?, ?, ?, ?)",
                (dim, val, _SPOTIFY_SEED_CONFIDENCE, time.time()),
            )
            seeded.append(dim)

        conn.commit()
        logger.info(
            "Spotify taste seed: %d dims seeded (matched %d/%d spotify tracks)",
            len(seeded), matched, matched + unmatched,
        )
        return {"seeded": seeded, "skipped": skipped, "matched": matched,
                "unmatched": unmatched, "total_weight": round(total_weight, 2)}
    finally:
        conn.close()


def seed_taste_from_library(overwrite_existing: bool = False) -> Dict[str, Any]:
    """Derive a taste profile from the mean of all track_scores in the library.

    This is the *cold-start* path: when the user has never played anything
    through Lyra, use their curated library as a signal.  A track someone
    bothered to acquire is implicit evidence of taste.

    Args:
        overwrite_existing: When False (default) only seeds dimensions that
            have confidence < 0.3 (i.e. never been meaningfully updated by
            real playback).  When True rewrites all dimensions.

    Returns:
        Dict with keys: seeded (list of dim names), skipped (list), total.
    """
    conn = get_connection(timeout=10.0)
    try:
        c = conn.cursor()

        # Compute per-dimension mean from all scored tracks
        cols = ", ".join(f"AVG({d})" for d in DIMENSIONS)
        c.execute(f"SELECT {cols} FROM track_scores")
        row = c.fetchone()
        if not row or all(v is None for v in row):
            return {"seeded": [], "skipped": [], "total": 0, "reason": "no_scored_tracks"}

        averages: Dict[str, float] = {}
        for dim, val in zip(DIMENSIONS, row):
            if val is not None:
                # track_scores are 0..1; convert to -1..1 preference space
                averages[dim] = _to_pref(float(val))

        if get_write_mode() != "apply_allowed":
            return {"seeded": [], "skipped": list(averages.keys()), "total": len(averages), "reason": "write_blocked"}

        seeded: List[str] = []
        skipped: List[str] = []

        for dim, seed_val in averages.items():
            if not overwrite_existing:
                c.execute("SELECT confidence FROM taste_profile WHERE dimension = ?", (dim,))
                existing = c.fetchone()
                if existing and float(existing[0]) >= 0.5:
                    skipped.append(dim)
                    continue

            c.execute(
                "INSERT OR REPLACE INTO taste_profile (dimension, value, confidence, last_updated) "
                "VALUES (?, ?, ?, ?)",
                (dim, seed_val, _SEED_CONFIDENCE, time.time()),
            )
            seeded.append(dim)

        conn.commit()
        logger.info("Taste seed: %d dimensions seeded from library averages", len(seeded))
        return {"seeded": seeded, "skipped": skipped, "total": len(averages)}
    finally:
        conn.close()


def get_taste_profile() -> Dict[str, Any]:
    """Return the current taste profile with library context.

    Merges the learned ``taste_profile`` rows with aggregate library stats
    so the caller gets everything needed for a dashboard or radio seed in
    one call.  If taste_profile is sparse/low-confidence, dimensions are
    supplemented with library-derived averages so the result is always
    meaningful.

    Returns:
        Dict with keys:
            dimensions         — {dim: float (-1..1)}, all 10 dimensions
            confidence         — {dim: float (0..1)}
            source             — {dim: "learned"|"library"|"default"}
            genre_affinity     — [{genre, score}] top genres from library
            era_distribution   — {decade_label: track_count}
            top_artists        — [{artist, count}] top 10 library artists
            total_signals      — int, number of playback events recorded
            library_stats      — {total_tracks, scored_tracks}
            is_cold_start      — bool, True when profile is mostly seeded
    """
    conn = get_connection(timeout=10.0)
    try:
        c = conn.cursor()

        # --- Learned profile ---
        c.execute("SELECT dimension, value, confidence FROM taste_profile")
        learned: Dict[str, Dict[str, float]] = {}
        for dim, val, conf in c.fetchall():
            learned[dim] = {"value": float(val), "confidence": float(conf or 0)}

        # --- Library means as fallback ---
        cols = ", ".join(f"AVG({d})" for d in DIMENSIONS)
        c.execute(f"SELECT {cols} FROM track_scores")
        row = c.fetchone() or []
        lib_means: Dict[str, float] = {}
        for dim, val in zip(DIMENSIONS, row):
            if val is not None:
                lib_means[dim] = _to_pref(float(val))

        # --- Merge: use learned if confidence ≥ 0.3, else library mean ---
        dimensions: Dict[str, float] = {}
        confidence: Dict[str, float] = {}
        source: Dict[str, str] = {}
        cold_count = 0

        for dim in DIMENSIONS:
            entry = learned.get(dim)
            if entry and entry["confidence"] >= 0.5:
                dimensions[dim] = round(entry["value"], 4)
                confidence[dim] = round(entry["confidence"], 4)
                source[dim] = "learned"
            elif dim in lib_means:
                dimensions[dim] = round(lib_means[dim], 4)
                confidence[dim] = round(entry["confidence"] if entry else 0.0, 4)
                source[dim] = "library"
                cold_count += 1
            else:
                dimensions[dim] = 0.0
                confidence[dim] = 0.0
                source[dim] = "default"
                cold_count += 1

        # --- Playback signal count ---
        c.execute("SELECT COUNT(*) FROM playback_history")
        total_signals = c.fetchone()[0] or 0

        # --- Top genres ---
        # Primary: biographer cache (contains real genre tags from Last.fm / MusicBrainz)
        # Fallback: tracks.genre column (often NULL if not tagged)
        import json as _json
        genre_counts: Dict[str, int] = {}
        c.execute(
            "SELECT payload_json FROM enrich_cache WHERE provider='biographer' AND payload_json IS NOT NULL LIMIT 300"
        )
        for (pj,) in c.fetchall():
            try:
                genres_list = _json.loads(pj).get("genres") or []
                for g in genres_list[:5]:
                    if g:
                        genre_counts[g] = genre_counts.get(g, 0) + 1
            except Exception:
                pass

        if not genre_counts:
            # Fall back to tracks.genre column
            c.execute(
                "SELECT genre, COUNT(*) as cnt FROM tracks "
                "WHERE status=? AND genre IS NOT NULL AND genre != '' "
                "GROUP BY genre ORDER BY cnt DESC LIMIT 12",
                ("active",),
            )
            genre_counts = {r[0]: r[1] for r in c.fetchall()}

        genre_affinity = [
            {"genre": g, "score": cnt}
            for g, cnt in sorted(genre_counts.items(), key=lambda x: -x[1])[:12]
        ]

        # --- Era distribution (from year field) ---
        c.execute(
            "SELECT year, COUNT(*) as cnt FROM tracks "
            "WHERE status='active' AND year IS NOT NULL AND year != '' "
            "GROUP BY year ORDER BY year"
        )
        era_raw: Dict[str, int] = {}
        for year_str, cnt in c.fetchall():
            try:
                decade = f"{(int(str(year_str)[:4]) // 10) * 10}s"
                era_raw[decade] = era_raw.get(decade, 0) + cnt
            except (ValueError, TypeError):
                pass

        # --- Top artists by track count ---
        c.execute(
            "SELECT artist, COUNT(*) as cnt FROM tracks "
            "WHERE status='active' AND artist IS NOT NULL AND artist != '' "
            "GROUP BY artist ORDER BY cnt DESC LIMIT 10"
        )
        top_artists = [{"artist": r[0], "count": r[1]} for r in c.fetchall()]

        # --- Library totals ---
        c.execute("SELECT COUNT(*) FROM tracks WHERE status='active'")
        total_tracks = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM track_scores WHERE energy IS NOT NULL")
        scored_tracks = c.fetchone()[0] or 0

        return {
            "dimensions": dimensions,
            "confidence": confidence,
            "source": source,
            "genre_affinity": genre_affinity,
            "era_distribution": era_raw,
            "top_artists": top_artists,
            "total_signals": total_signals,
            "library_stats": {
                "total_tracks": total_tracks,
                "scored_tracks": scored_tracks,
            },
            "is_cold_start": cold_count > len(DIMENSIONS) // 2,
        }
    finally:
        conn.close()


def _to_pref(value_01: float) -> float:
    """Map a 0..1 dimension score to -1..1 taste preference space."""
    return float(max(-1.0, min(1.0, (float(value_01) * 2.0) - 1.0)))


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _fetch_track_scores(conn, track_id: str) -> Optional[Dict[str, float]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
            FROM track_scores
            WHERE track_id = ?
            """,
            (track_id,),
        )
    except Exception:
        return None

    row = cur.fetchone()
    if not row:
        return None

    keys = ["energy", "valence", "tension", "density", "warmth", "movement", "space", "rawness", "complexity", "nostalgia"]
    out: Dict[str, float] = {}
    for k, v in zip(keys, row):
        if v is None:
            continue
        out[k] = float(v)

    return out if out else None


def update_taste_from_playback(
    track_id: str,
    *,
    positive: bool,
    weight: float = 1.0,
) -> Dict[str, Any]:
    """Update taste_profile based on a playback event.

    Args:
        track_id: Track ID
        positive: True if liked/completed, False if skipped/disliked
        weight: Strength multiplier

    Returns:
        Stats dict.
    """

    track_id = (track_id or "").strip()
    if not track_id:
        return {"updated": 0, "reason": "missing_track_id"}

    conn = get_connection(timeout=10.0)
    scores = _fetch_track_scores(conn, track_id)
    if not scores:
        conn.close()
        return {"updated": 0, "reason": "missing_track_scores"}

    if get_write_mode() != "apply_allowed":
        conn.close()
        return {"updated": 0, "reason": "write_blocked", "write_mode": get_write_mode()}

    # Learning rate: small and bounded.
    w = float(_clamp(weight, 0.1, 3.0))
    lr = 0.08 * w

    updated = 0
    cur = conn.cursor()

    for dim, v01 in scores.items():
        target = _to_pref(v01)
        if not positive:
            # Negative signal: push away from the track's vector.
            target = -target

        cur.execute("SELECT value, confidence FROM taste_profile WHERE dimension = ?", (dim,))
        row = cur.fetchone()
        if row:
            current_value = float(row[0])
            current_conf = float(row[1] or 0.5)
        else:
            current_value = 0.0
            current_conf = 0.2

        # EMA update
        new_value = (1.0 - lr) * current_value + lr * target
        new_value = float(_clamp(new_value, -1.0, 1.0))

        # Confidence creeps upward slowly with each update
        new_conf = float(_clamp(current_conf + (0.01 * w), 0.0, 1.0))

        cur.execute(
            """
            INSERT OR REPLACE INTO taste_profile (dimension, value, confidence, last_updated)
            VALUES (?, ?, ?, ?)
            """,
            (dim, new_value, new_conf, time.time()),
        )
        updated += 1

    conn.commit()
    conn.close()

    return {"updated": updated, "dimensions": list(scores.keys()), "positive": bool(positive)}
