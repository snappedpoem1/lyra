"""oracle.ingest_confidence — Ingest trust lifecycle state machine.

Tracks the confidence pipeline for every acquired audio file:
    acquired → validated → normalized → enriched → placed
                  ↓            ↓           ↓
              rejected     rejected    rejected

See docs/specs/SPEC-007_INGEST_CONFIDENCE.md for the full contract.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Valid states ────────────────────────────────────────────────────────────
STATES = ("acquired", "validated", "normalized", "enriched", "placed", "rejected")

# Minimum minutes before a non-terminal state is considered "stalled"
STALL_THRESHOLD_MINUTES = 30


def _get_conn():
    from oracle.db.schema import get_connection
    return get_connection(timeout=10.0)


# ── Core write ──────────────────────────────────────────────────────────────

def record_transition(
    filepath: str,
    state: str,
    reason_codes: List[str],
    track_id: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Write one lifecycle transition row to `ingest_confidence`.

    Args:
        filepath: Canonical file path at the time of this transition.
        state: One of STATES.
        reason_codes: Non-empty list of reason code strings.
        track_id: Set for normalized/enriched/placed states once the DB row exists.
        source: Human-readable origin label (e.g. "Artist - Title" from the queue row).
    """
    if state not in STATES:
        logger.warning("[ingest-confidence] unknown state %r; skipping", state)
        return
    codes_json = json.dumps(reason_codes)
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO ingest_confidence (track_id, filepath, state, reason_codes, source, transitioned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (track_id, str(filepath), state, codes_json, source, time.time()),
        )
        conn.commit()
        logger.debug(
            "[ingest-confidence] %s → %s reason=%r track_id=%s",
            filepath, state, reason_codes, track_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ingest-confidence] failed to record transition: %s", exc)
    finally:
        conn.close()


# ── Backfill ─────────────────────────────────────────────────────────────────

def backfill_placed_tracks() -> int:
    """Write a `placed` / backfill row for every existing track with no confidence record.

    Returns the number of rows written.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.track_id, t.filepath
            FROM tracks t
            WHERE t.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM ingest_confidence ic WHERE ic.filepath = t.filepath
              )
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return 0

    written = 0
    now = time.time()
    codes_json = json.dumps(["backfill"])
    conn = _get_conn()
    try:
        for track_id, filepath in rows:
            conn.execute(
                """
                INSERT INTO ingest_confidence (track_id, filepath, state, reason_codes, source, transitioned_at)
                VALUES (?, ?, 'placed', ?, 'backfill', ?)
                """,
                (track_id, filepath, codes_json, now),
            )
            written += 1
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ingest-confidence] backfill failed: %s", exc)
        written = 0
    finally:
        conn.close()

    logger.info("[ingest-confidence] backfill wrote %d placed rows", written)
    return written


# ── Queries ──────────────────────────────────────────────────────────────────

def get_confidence_summary() -> Dict[str, Any]:
    """Return aggregate counts by most-recent state per unique filepath.

    Also returns stalled count (non-terminal states older than STALL_THRESHOLD_MINUTES).
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT ic.state, COUNT(*) as cnt
            FROM ingest_confidence ic
            WHERE ic.id = (
                SELECT MAX(id) FROM ingest_confidence WHERE filepath = ic.filepath
            )
            GROUP BY ic.state
            """
        ).fetchall()

        stall_cutoff = time.time() - (STALL_THRESHOLD_MINUTES * 60)
        stalled = conn.execute(
            """
            SELECT COUNT(*) FROM ingest_confidence ic
            WHERE ic.id = (
                SELECT MAX(id) FROM ingest_confidence WHERE filepath = ic.filepath
            )
              AND ic.state NOT IN ('placed', 'rejected')
              AND ic.transitioned_at < ?
            """,
            (stall_cutoff,),
        ).fetchone()[0]

        total = conn.execute(
            "SELECT COUNT(DISTINCT filepath) FROM ingest_confidence"
        ).fetchone()[0]

        backfill_count = conn.execute(
            "SELECT COUNT(*) FROM ingest_confidence WHERE reason_codes LIKE '%backfill%'"
        ).fetchone()[0]
    finally:
        conn.close()

    summary: Dict[str, int] = {s: 0 for s in STATES}
    for state, cnt in rows:
        if state in summary:
            summary[state] = int(cnt)

    return {
        "summary": summary,
        "stalled": int(stalled),
        "total_unique_filepaths": int(total),
        "backfill_count": int(backfill_count),
    }


def get_recent_transitions(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent N transitions, newest first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT filepath, track_id, state, reason_codes, transitioned_at
            FROM ingest_confidence
            ORDER BY transitioned_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "filepath": row[0],
            "track_id": row[1],
            "state": row[2],
            "reason_codes": json.loads(row[3]) if row[3] else [],
            "transitioned_at": row[4],
        }
        for row in rows
    ]
