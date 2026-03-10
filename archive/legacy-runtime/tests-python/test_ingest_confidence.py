"""Tests for oracle.ingest_confidence — SPEC-007 state machine.

Uses an isolated in-memory SQLite database for every test to avoid touching
the real registry DB.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Generator
from unittest.mock import patch

import pytest

import oracle.ingest_confidence as ic

# ── DB fixture ──────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ingest_confidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT,
    filepath TEXT NOT NULL,
    state TEXT NOT NULL,
    reason_codes TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    transitioned_at REAL DEFAULT (strftime('%s', 'now'))
);
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY,
    filepath TEXT NOT NULL,
    status TEXT DEFAULT 'active'
);
"""


@pytest.fixture()
def mem_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield an in-memory SQLite connection with the required tables."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_CREATE_TABLE)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class _NoCloseProxy:
    """Wraps a SQLite connection but makes close() a no-op.

    Used in tests to prevent the shared in-memory connection from being closed
    between module calls.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:  # no-op  # noqa: D401
        pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


@pytest.fixture(autouse=True)
def patch_conn(mem_conn: sqlite3.Connection):
    """Route all _get_conn() calls in ingest_confidence to a no-close proxy.

    The module calls conn.close() after each operation. _NoCloseProxy absorbs
    those calls so the shared in-memory connection stays open for the whole test.
    """
    proxy = _NoCloseProxy(mem_conn)
    with patch.object(ic, "_get_conn", return_value=proxy):
        yield


# ── record_transition ────────────────────────────────────────────────────────

class TestRecordTransition:
    def test_writes_row(self, mem_conn: sqlite3.Connection) -> None:
        ic.record_transition("/music/track.flac", "acquired", ["file_detected"])
        rows = mem_conn.execute("SELECT * FROM ingest_confidence").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["filepath"] == "/music/track.flac"
        assert row["state"] == "acquired"
        assert json.loads(row["reason_codes"]) == ["file_detected"]
        assert row["track_id"] is None

    def test_with_track_id_and_source(self, mem_conn: sqlite3.Connection) -> None:
        ic.record_transition(
            "/music/track.flac",
            "placed",
            ["scan_complete", "embedding_indexed"],
            track_id="abc123",
            source="Artist - Title",
        )
        row = mem_conn.execute("SELECT * FROM ingest_confidence").fetchone()
        assert row["track_id"] == "abc123"
        assert row["source"] == "Artist - Title"
        assert "scan_complete" in json.loads(row["reason_codes"])

    def test_unknown_state_skips(self, mem_conn: sqlite3.Connection) -> None:
        ic.record_transition("/music/track.flac", "not_a_real_state", ["code"])
        count = mem_conn.execute("SELECT COUNT(*) FROM ingest_confidence").fetchone()[0]
        assert count == 0

    def test_multiple_transitions_same_file(self, mem_conn: sqlite3.Connection) -> None:
        for state, code in [
            ("acquired", "file_detected"),
            ("validated", "guard_pass"),
            ("normalized", "moved_to_library"),
        ]:
            ic.record_transition("/music/track.flac", state, [code])
        rows = mem_conn.execute(
            "SELECT state FROM ingest_confidence ORDER BY id"
        ).fetchall()
        assert [r[0] for r in rows] == ["acquired", "validated", "normalized"]

    def test_rejected_state_written(self, mem_conn: sqlite3.Connection) -> None:
        ic.record_transition("/drop/bad.mp3", "rejected", ["guard_junk"])
        row = mem_conn.execute("SELECT * FROM ingest_confidence").fetchone()
        assert row["state"] == "rejected"
        assert json.loads(row["reason_codes"]) == ["guard_junk"]


# ── backfill_placed_tracks ────────────────────────────────────────────────────

class TestBackfillPlacedTracks:
    def test_backfills_existing_tracks(self, mem_conn: sqlite3.Connection) -> None:
        # Insert two tracks with no confidence rows
        mem_conn.execute(
            "INSERT INTO tracks (track_id, filepath) VALUES ('t1', '/lib/a.flac')"
        )
        mem_conn.execute(
            "INSERT INTO tracks (track_id, filepath) VALUES ('t2', '/lib/b.flac')"
        )
        mem_conn.commit()

        n = ic.backfill_placed_tracks()
        assert n == 2

        rows = mem_conn.execute(
            "SELECT filepath, state, reason_codes, track_id FROM ingest_confidence"
        ).fetchall()
        filepaths = {r["filepath"] for r in rows}
        assert "/lib/a.flac" in filepaths
        assert "/lib/b.flac" in filepaths
        for row in rows:
            assert row["state"] == "placed"
            codes = json.loads(row["reason_codes"])
            assert "backfill" in codes
            assert row["track_id"] is not None

    def test_no_duplicate_backfill(self, mem_conn: sqlite3.Connection) -> None:
        mem_conn.execute(
            "INSERT INTO tracks (track_id, filepath) VALUES ('t1', '/lib/a.flac')"
        )
        mem_conn.commit()
        # Pre-existing confidence row — should be excluded
        mem_conn.execute(
            "INSERT INTO ingest_confidence (track_id, filepath, state, reason_codes) "
            "VALUES ('t1', '/lib/a.flac', 'placed', '[\"scan_complete\"]')"
        )
        mem_conn.commit()

        n = ic.backfill_placed_tracks()
        assert n == 0

    def test_empty_tracks_returns_zero(self, mem_conn: sqlite3.Connection) -> None:
        n = ic.backfill_placed_tracks()
        assert n == 0


# ── get_confidence_summary ────────────────────────────────────────────────────

class TestGetConfidenceSummary:
    def test_empty_db(self, mem_conn: sqlite3.Connection) -> None:
        result = ic.get_confidence_summary()
        # All states are present with zero counts even when the table is empty
        assert all(result["summary"].get(s, -1) == 0 for s in ic.STATES)
        assert result["stalled"] == 0
        assert result["total_unique_filepaths"] == 0
        assert "backfill_count" in result

    def test_counts_states(self, mem_conn: sqlite3.Connection) -> None:
        for state, fp in [
            ("placed", "/lib/a.flac"),
            ("placed", "/lib/b.flac"),
            ("rejected", "/drop/c.mp3"),
        ]:
            ic.record_transition(fp, state, ["code"])

        result = ic.get_confidence_summary()
        assert result["summary"]["placed"] == 2
        assert result["summary"]["rejected"] == 1

    def test_stall_detection(self, mem_conn: sqlite3.Connection) -> None:
        # Insert an 'acquired' row with an old timestamp
        old_ts = time.time() - (ic.STALL_THRESHOLD_MINUTES + 5) * 60
        mem_conn.execute(
            "INSERT INTO ingest_confidence (filepath, state, reason_codes, transitioned_at) "
            "VALUES ('/drop/stalled.flac', 'acquired', '[\"file_detected\"]', ?)",
            (old_ts,),
        )
        mem_conn.commit()

        result = ic.get_confidence_summary()
        assert result["stalled"] >= 1


# ── get_recent_transitions ────────────────────────────────────────────────────

class TestGetRecentTransitions:
    def test_returns_newest_first(self, mem_conn: sqlite3.Connection) -> None:
        for i, fp in enumerate(["/a.flac", "/b.flac", "/c.flac"]):
            mem_conn.execute(
                "INSERT INTO ingest_confidence (filepath, state, reason_codes, transitioned_at) "
                "VALUES (?, 'acquired', '[]', ?)",
                (fp, float(i)),
            )
        mem_conn.commit()

        rows = ic.get_recent_transitions(limit=10)
        # Should be newest first (highest transitioned_at first)
        assert rows[0]["filepath"] == "/c.flac"
        assert rows[-1]["filepath"] == "/a.flac"

    def test_limit_respected(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(10):
            mem_conn.execute(
                "INSERT INTO ingest_confidence (filepath, state, reason_codes, transitioned_at) "
                "VALUES (?, 'placed', '[]', ?)",
                (f"/track{i}.flac", float(i)),
            )
        mem_conn.commit()

        rows = ic.get_recent_transitions(limit=5)
        assert len(rows) == 5

    def test_reason_codes_deserialized(self, mem_conn: sqlite3.Connection) -> None:
        ic.record_transition("/t.flac", "placed", ["scan_complete", "scored"])
        rows = ic.get_recent_transitions(limit=1)
        assert isinstance(rows[0]["reason_codes"], list)
        assert "scan_complete" in rows[0]["reason_codes"]
