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
from typing import Any, Dict, Optional

from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)


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
