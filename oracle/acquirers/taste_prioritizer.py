"""Taste-driven acquisition queue prioritizer.

Re-scores acquisition_queue items by how well each artist/title aligns with
the user's current taste_profile. Items matching high-energy, high-valence,
or otherwise taste-aligned content bubble to the top.

Two-pass strategy:
  Pass A: artist already exists in local library → score by average track dims
  Pass B: unknown artist → score by genre-tag heuristics mapped to dimensions

Priority scale: 0.0–10.0 (default queue items start at 5.0).
Taste-boosted items: 6.0–9.5 depending on signal strength.
Demoted items: 1.0–4.5.

Usage:
    from oracle.acquirers.taste_prioritizer import prioritize_queue, get_next_priority_batch
    stats = prioritize_queue()
    batch = get_next_priority_batch(limit=10)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

# Dimensions with highest taste signal weight for queue alignment
_KEY_DIMS = ("energy", "valence", "warmth", "movement")

# Genre keywords → rough dimension boosts (additive to base score)
_GENRE_BOOSTS: Dict[str, Dict[str, float]] = {
    "hip-hop": {"energy": 0.6, "rawness": 0.7, "density": 0.4},
    "rap": {"energy": 0.6, "rawness": 0.7, "density": 0.4},
    "electronic": {"energy": 0.7, "movement": 0.8, "tension": 0.5},
    "edm": {"energy": 0.8, "movement": 0.9, "tension": 0.6},
    "pop": {"valence": 0.7, "warmth": 0.5, "density": 0.3},
    "rock": {"energy": 0.6, "rawness": 0.5, "tension": 0.4},
    "jazz": {"complexity": 0.8, "warmth": 0.6, "nostalgia": 0.5},
    "classical": {"complexity": 0.9, "space": 0.8, "tension": 0.3},
    "r&b": {"warmth": 0.7, "valence": 0.6, "movement": 0.5},
    "soul": {"warmth": 0.8, "rawness": 0.4, "nostalgia": 0.6},
    "ambient": {"space": 0.9, "energy": 0.1, "tension": 0.1},
    "metal": {"energy": 0.9, "rawness": 0.9, "tension": 0.8},
    "indie": {"rawness": 0.5, "nostalgia": 0.4, "complexity": 0.4},
    "folk": {"warmth": 0.7, "nostalgia": 0.6, "rawness": 0.4},
    "blues": {"rawness": 0.6, "warmth": 0.7, "nostalgia": 0.7},
}

_ALL_DIMS = (
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness", "complexity", "nostalgia",
)


def _get_taste_profile(conn) -> Optional[Dict[str, float]]:
    """Load taste_profile from DB as {dimension: value} dict."""
    cursor = conn.cursor()
    cursor.execute("SELECT dimension, value FROM taste_profile")
    rows = cursor.fetchall()
    if not rows:
        return None
    return {row[0]: float(row[1]) for row in rows}


def _get_artist_avg_scores(conn, artist: str) -> Optional[Dict[str, float]]:
    """Get average score dimensions for a known artist's tracks."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            AVG(ts.energy), AVG(ts.valence), AVG(ts.tension), AVG(ts.density),
            AVG(ts.warmth), AVG(ts.movement), AVG(ts.space), AVG(ts.rawness),
            AVG(ts.complexity), AVG(ts.nostalgia)
        FROM track_scores ts
        JOIN tracks t ON t.track_id = ts.track_id
        WHERE LOWER(t.artist) LIKE LOWER(?)
          AND t.status = 'active'
          AND ts.energy IS NOT NULL
        """,
        (f"%{artist}%",),
    )
    row = cursor.fetchone()
    if not row or row[0] is None:
        return None
    return dict(zip(_ALL_DIMS, (float(v) if v is not None else 0.5 for v in row)))


def _genre_score_vector(genre_hint: str) -> Dict[str, float]:
    """Build a pseudo-score vector from genre keyword hints."""
    base = {dim: 0.5 for dim in _ALL_DIMS}
    genre_lower = genre_hint.lower()
    for keyword, boosts in _GENRE_BOOSTS.items():
        if keyword in genre_lower:
            for dim, val in boosts.items():
                base[dim] = max(base[dim], val)
    return base


def _cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two dimension dicts."""
    dims = set(a) & set(b)
    if not dims:
        return 0.0
    dot = sum(a[d] * b[d] for d in dims)
    mag_a = math.sqrt(sum(a[d] ** 2 for d in dims))
    mag_b = math.sqrt(sum(b[d] ** 2 for d in dims))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _compute_priority(
    taste: Dict[str, float],
    track_scores: Dict[str, float],
    base_priority: float = 5.0,
) -> float:
    """Compute a priority score [0..10] by comparing taste to track scores.

    Cosine similarity of 1.0 → priority 9.5
    Similarity of 0.0 → priority 1.0
    Neutral (0.5) → close to base_priority
    """
    similarity = _cosine_similarity(taste, track_scores)
    # Rescale: similarity in [0,1] → priority in [1, 9.5]
    return round(1.0 + similarity * 8.5, 2)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def prioritize_queue(limit: int = 0) -> Dict[str, Any]:
    """Re-score all pending acquisition_queue items by taste alignment.

    Args:
        limit: Max items to update. 0 = all pending.

    Returns:
        Stats dict: updated, skipped, no_taste.
    """
    conn = get_connection(timeout=15.0)

    taste = _get_taste_profile(conn)
    if not taste:
        conn.close()
        logger.warning("[prioritize] no taste_profile data — skipping")
        return {"updated": 0, "skipped": 0, "no_taste": True}

    cursor = conn.cursor()
    query = (
        "SELECT id, artist, title, album FROM acquisition_queue "
        "WHERE status = 'pending' "
    ) + ("LIMIT ?" if limit > 0 else "")
    params = (limit,) if limit > 0 else ()
    cursor.execute(query, params)
    items = cursor.fetchall()

    updated = 0
    skipped = 0

    for item_id, artist, title, album in items:
        if not artist:
            skipped += 1
            continue

        # Pass A: known artist
        scores = _get_artist_avg_scores(conn, artist)

        # Pass B: genre hint from album/title string
        if scores is None:
            genre_hint = f"{album or ''} {title or ''}".strip()
            scores = _genre_score_vector(genre_hint)

        new_priority = _compute_priority(taste, scores)
        cursor.execute(
            "UPDATE acquisition_queue SET priority=? WHERE id=?",
            (new_priority, item_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    logger.info("[prioritize] updated=%d skipped=%d", updated, skipped)
    return {"updated": updated, "skipped": skipped, "no_taste": False}


def get_next_priority_batch(
    limit: int = 10,
    status: str = "pending",
) -> List[Dict[str, Any]]:
    """Return the next N highest-priority queue items.

    Args:
        limit: Number of items to return.
        status: Queue status to filter on.

    Returns:
        List of dicts with id, artist, title, album, priority.
    """
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, artist, title, album, priority
        FROM acquisition_queue
        WHERE status = ?
        ORDER BY priority DESC, id ASC
        LIMIT ?
        """,
        (status, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "artist": r[1], "title": r[2], "album": r[3], "priority": r[4]}
        for r in rows
    ]
