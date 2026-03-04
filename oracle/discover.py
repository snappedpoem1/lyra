"""Oracle Discovery Engine — find music you don't know about.

The core intelligence loop:
    1. Mine Spotify history for the user's top artists (by listening time)
    2. Traverse the connections graph from those artists
    3. Find connected artists NOT in the user's library
    4. Score by taste fit + connection strength + cultural relevance
    5. Return ranked suggestions with real reasons

This is what makes it an oracle — not a grabber, not a search box.
It tells you what you don't know that you should know.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

DIMENSIONS = [
    "energy", "valence", "tension", "density", "warmth",
    "movement", "space", "rawness", "complexity", "nostalgia",
]


def oracle_discover(
    limit: int = 30,
    min_connection_weight: float = 0.3,
    seed_artist: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run the oracle discovery pipeline.

    Args:
        limit: Maximum suggestions to return.
        min_connection_weight: Minimum connection weight to follow.
        seed_artist: Optional single artist to seed from (otherwise uses
            top Spotify artists by listening time).

    Returns:
        List of discovery suggestions, each with:
            artist, connection_from, connection_type, weight,
            reason, score, in_library (bool), tracks_available (int)
    """
    conn = get_connection(timeout=30.0)
    try:
        c = conn.cursor()

        # ── Step 1: Identify seed artists ──────────────────────────────
        if seed_artist:
            seed_artists = [(seed_artist, 100000, 100)]
        else:
            # Top artists from Spotify by total listening time
            c.execute("""
                SELECT artist, SUM(ms_played) as total_ms, COUNT(*) as plays
                FROM spotify_history
                WHERE ms_played > 30000
                  AND artist IS NOT NULL AND artist != ''
                GROUP BY artist
                ORDER BY total_ms DESC
                LIMIT 100
            """)
            seed_artists = [(row[0], row[1], row[2]) for row in c.fetchall()]

        if not seed_artists:
            return []

        # Build set of artists already in library (lowercase for matching)
        c.execute("SELECT DISTINCT LOWER(artist) FROM tracks WHERE status = 'active'")
        library_artists = {row[0] for row in c.fetchall()}

        # Build set of artists already in acquisition queue
        c.execute("SELECT DISTINCT LOWER(artist) FROM acquisition_queue")
        queued_artists = {row[0] for row in c.fetchall()}

        # ── Step 2: Traverse connections graph ─────────────────────────
        # For each seed artist, find who they're connected to
        discoveries: Dict[str, Dict[str, Any]] = {}

        for artist_name, total_ms, play_count in seed_artists:
            artist_lower = artist_name.strip().lower()
            listen_weight = math.log1p(total_ms / 60000.0)  # log(1 + minutes)

            # Query connections in both directions
            c.execute("""
                SELECT target, type, weight, evidence FROM connections
                WHERE LOWER(source) = ? AND weight >= ?
                UNION
                SELECT source, type, weight, evidence FROM connections
                WHERE LOWER(target) = ? AND weight >= ?
            """, (artist_lower, min_connection_weight,
                  artist_lower, min_connection_weight))

            for target, conn_type, conn_weight, evidence in c.fetchall():
                target_lower = target.strip().lower()

                # Skip if it's the seed artist itself
                if target_lower == artist_lower:
                    continue

                # Skip if already in library
                if target_lower in library_artists:
                    continue

                # Compute discovery score:
                # - Connection weight (how strong the link is)
                # - Listen weight (how much you listen to the seed artist)
                # - Connection type bonus (collab > member_of > influence)
                type_bonus = {
                    "collab": 1.3,
                    "member_of": 1.0,
                    "influence": 0.8,
                    "rivalry": 0.4,
                }.get(conn_type, 0.7)

                score = (
                    float(conn_weight) * type_bonus *
                    min(listen_weight / 5.0, 1.5)  # cap so mega-rotation doesn't dominate
                )

                # Build reason text
                reason = _build_reason(
                    target, artist_name, conn_type, evidence
                )

                key = target_lower
                if key in discoveries:
                    # Multiple connections to same artist? Keep best + accumulate reasons
                    existing = discoveries[key]
                    existing["score"] = max(existing["score"], score)
                    if reason not in existing["reasons"]:
                        existing["reasons"].append(reason)
                    if artist_name not in existing["connected_from"]:
                        existing["connected_from"].append(artist_name)
                else:
                    discoveries[key] = {
                        "artist": target,
                        "connected_from": [artist_name],
                        "connection_type": conn_type,
                        "weight": float(conn_weight),
                        "score": score,
                        "reasons": [reason],
                        "already_queued": target_lower in queued_artists,
                    }

        # ── Step 3: Also find Spotify artists not in library ──────────
        # These are artists you actively listen to but haven't acquired
        spotify_only: List[Dict[str, Any]] = []
        for artist_name, total_ms, play_count in seed_artists[:200]:
            artist_lower = artist_name.strip().lower()
            if artist_lower not in library_artists and artist_lower not in discoveries:
                listen_hours = total_ms / 3_600_000
                if listen_hours >= 0.5:  # At least 30 min total listening
                    spotify_only.append({
                        "artist": artist_name,
                        "connected_from": ["Your Spotify history"],
                        "connection_type": "spotify_favorite",
                        "weight": min(listen_hours / 10.0, 1.0),
                        "score": math.log1p(listen_hours) * 0.8,
                        "reasons": [
                            f"You've listened to {artist_name} for "
                            f"{listen_hours:.1f} hours on Spotify "
                            f"({play_count} plays) but don't have them locally."
                        ],
                        "already_queued": artist_lower in queued_artists,
                    })

        # ── Step 4: Merge, sort, and enrich ────────────────────────────
        all_results = list(discoveries.values()) + spotify_only

        # Add taste alignment if taste profile exists
        taste = _load_taste_profile(c)
        if taste:
            for item in all_results:
                # Can't compute exact taste fit without tracks, but we can
                # boost items connected to artists whose scored tracks
                # align with taste
                for seed_name in item["connected_from"]:
                    alignment = _seed_artist_taste_alignment(c, seed_name, taste)
                    if alignment > 0:
                        item["score"] *= (1.0 + alignment * 0.3)
                        if alignment > 0.6:
                            item["reasons"].append(
                                f"Sonically aligned with your taste profile "
                                f"(via {seed_name}, alignment: {alignment:.0%})"
                            )

        # Sort by score descending
        all_results.sort(key=lambda x: -x["score"])

        # Final output
        output: List[Dict[str, Any]] = []
        for item in all_results[:limit]:
            output.append({
                "artist": item["artist"],
                "connected_from": item["connected_from"],
                "connection_type": item["connection_type"],
                "weight": round(item["weight"], 3),
                "score": round(item["score"], 4),
                "reasons": item["reasons"],
                "already_queued": item["already_queued"],
            })

        logger.info(
            "Oracle discovery: %d suggestions from %d seed artists "
            "(%d graph, %d spotify-only)",
            len(output), len(seed_artists),
            len(discoveries), len(spotify_only),
        )
        return output
    finally:
        conn.close()


def _build_reason(
    target: str, source: str, conn_type: str, evidence: Optional[str]
) -> str:
    """Build a human-readable reason for a discovery suggestion."""
    type_phrases = {
        "collab": f"{target} collaborated with {source}",
        "member_of": f"{target} is/was a member of {source} (or vice versa)",
        "influence": f"{target} is musically influenced by {source}",
        "rivalry": f"{target} and {source} are artistic rivals in the same scene",
    }
    base = type_phrases.get(conn_type, f"{target} is connected to {source}")

    if evidence:
        # Try to extract useful info from evidence JSON
        try:
            import json
            ev = json.loads(evidence)
            if isinstance(ev, dict):
                detail = ev.get("detail") or ev.get("relationship") or ev.get("type")
                if detail:
                    base += f" — {detail}"
        except (ValueError, TypeError):
            if len(evidence) < 200:
                base += f" ({evidence})"

    return base


def _load_taste_profile(cursor) -> Optional[Dict[str, float]]:
    """Load the taste profile as {dimension: value(-1..1)}."""
    try:
        cursor.execute(
            "SELECT dimension, value, confidence FROM taste_profile "
            "WHERE confidence >= 0.3"
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        return {dim: float(val) for dim, val, _ in rows}
    except Exception:
        return None


def _seed_artist_taste_alignment(
    cursor, artist_name: str, taste: Dict[str, float]
) -> float:
    """Compute how well a seed artist's scored tracks align with taste.

    Returns 0..1 alignment score.
    """
    try:
        cols = ", ".join(f"AVG(ts.{d})" for d in DIMENSIONS)
        cursor.execute(f"""
            SELECT {cols}
            FROM tracks t
            JOIN track_scores ts ON t.track_id = ts.track_id
            WHERE LOWER(t.artist) = ? AND t.status = 'active'
        """, (artist_name.strip().lower(),))
        row = cursor.fetchone()
        if not row or all(v is None for v in row):
            return 0.0

        total_alignment = 0.0
        count = 0
        for dim, avg_score in zip(DIMENSIONS, row):
            if avg_score is None or dim not in taste:
                continue
            # Convert score (0..1) to pref space (-1..1) for comparison
            score_pref = (float(avg_score) * 2.0) - 1.0
            taste_pref = taste[dim]
            alignment = 1.0 - abs(score_pref - taste_pref) / 2.0  # 0..1
            total_alignment += alignment
            count += 1

        return total_alignment / count if count > 0 else 0.0
    except Exception:
        return 0.0
