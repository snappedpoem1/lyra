"""Tests for oracle.enrichers.mb_identity — Wave 10 MBID Identity Spine.

All tests use an isolated in-memory SQLite database routed through a
no-close proxy so the shared connection stays alive across module calls.
``enrich_by_text`` is always mocked to keep tests offline and fast.
"""

from __future__ import annotations

import sqlite3
from typing import Generator
from unittest.mock import patch

import pytest

from oracle.enrichers.mb_identity import MBIDStats, MBIdentityResolver
from oracle.enrichers.musicbrainz import RecordingMatch

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_TRACKS_DDL = """
CREATE TABLE IF NOT EXISTS tracks (
    track_id            TEXT PRIMARY KEY,
    artist              TEXT,
    title               TEXT,
    album               TEXT,
    duration            REAL,
    status              TEXT DEFAULT 'active',
    recording_mbid      TEXT,
    artist_mbid         TEXT,
    release_mbid        TEXT,
    release_group_mbid  TEXT,
    isrc                TEXT,
    last_enriched_at    REAL,
    last_seen_at        REAL
);
"""


class _NoCloseProxy:
    """Wraps a SQLite connection; makes ``close()`` a no-op."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:  # no-op
        pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


@pytest.fixture()
def mem_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield an in-memory SQLite connection with the tracks table."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_TRACKS_DDL)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def patch_get_conn(mem_conn: sqlite3.Connection):
    """Route all get_connection() calls in mb_identity to the in-memory DB."""
    proxy = _NoCloseProxy(mem_conn)
    with patch("oracle.enrichers.mb_identity.get_connection", return_value=proxy):
        yield


def _insert_track(
    conn: sqlite3.Connection,
    track_id: str,
    artist: str = "Test Artist",
    title: str = "Test Track",
    album: str = "Test Album",
    duration: float = 180.0,
    status: str = "active",
    recording_mbid: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO tracks (track_id, artist, title, album, duration, status, recording_mbid)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (track_id, artist, title, album, duration, status, recording_mbid),
    )
    conn.commit()


def _make_match(
    recording_mbid: str = "rec-1111",
    artist_mbid: str = "art-2222",
    isrc: str = "USRC12345678",
    confidence: float = 0.85,
) -> RecordingMatch:
    return RecordingMatch(
        recording_mbid=recording_mbid,
        artist_mbid=artist_mbid,
        isrc=isrc,
        confidence=confidence,
        source="musicbrainz_text",
    )


# ---------------------------------------------------------------------------
# resolve_batch — happy path
# ---------------------------------------------------------------------------


class TestResolveBatch:
    def test_happy_path_writes_mbids(self, mem_conn: sqlite3.Connection) -> None:
        """Successful match writes recording_mbid, artist_mbid, isrc, last_enriched_at."""
        _insert_track(mem_conn, "t1")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=_make_match(),
        ):
            result = MBIdentityResolver().resolve_batch(limit=10)

        assert result.resolved == 1
        assert result.no_match == 0
        assert result.failed == 0

        row = mem_conn.execute("SELECT * FROM tracks WHERE track_id='t1'").fetchone()
        assert row["recording_mbid"] == "rec-1111"
        assert row["artist_mbid"] == "art-2222"
        assert row["isrc"] == "USRC12345678"
        assert row["last_enriched_at"] is not None
        assert row["last_enriched_at"] > 0

    def test_multiple_tracks_all_resolved(self, mem_conn: sqlite3.Connection) -> None:
        for i in range(3):
            _insert_track(mem_conn, f"t{i}")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=_make_match(),
        ):
            result = MBIdentityResolver().resolve_batch(limit=10)

        assert result.resolved == 3
        assert result.total_eligible == 3


# ---------------------------------------------------------------------------
# resolve_batch — only_missing flag
# ---------------------------------------------------------------------------


class TestResolveBatchOnlyMissing:
    def test_skips_tracks_with_existing_recording_mbid(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "existing", recording_mbid="already-set")
        _insert_track(mem_conn, "fresh")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=_make_match(),
        ) as mock_et:
            result = MBIdentityResolver().resolve_batch(limit=10, only_missing=True)

        # Only the fresh track should have been processed
        assert result.total_eligible == 1
        assert result.resolved == 1
        assert mock_et.call_count == 1

    def test_all_flag_resolves_existing_tracks(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "existing", recording_mbid="already-set")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=_make_match(),
        ) as mock_et:
            result = MBIdentityResolver().resolve_batch(limit=10, only_missing=False)

        assert result.total_eligible == 1
        assert mock_et.call_count == 1


# ---------------------------------------------------------------------------
# resolve_batch — no match
# ---------------------------------------------------------------------------


class TestResolveBatchNoMatch:
    def test_no_match_increments_no_match_counter(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "t1")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=None,
        ):
            result = MBIdentityResolver().resolve_batch(limit=10)

        assert result.no_match == 1
        assert result.resolved == 0

    def test_no_match_still_stamps_last_enriched_at(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "t1")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=None,
        ):
            MBIdentityResolver().resolve_batch(limit=10)

        row = mem_conn.execute("SELECT last_enriched_at FROM tracks WHERE track_id='t1'").fetchone()
        assert row["last_enriched_at"] is not None

    def test_low_confidence_match_counts_as_no_match(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "t1")
        low_conf = _make_match(confidence=0.40)

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            return_value=low_conf,
        ):
            result = MBIdentityResolver().resolve_batch(limit=10, min_confidence=0.65)

        assert result.no_match == 1
        assert result.resolved == 0


# ---------------------------------------------------------------------------
# resolve_batch — exception handling
# ---------------------------------------------------------------------------


class TestResolveBatchExceptions:
    def test_exception_increments_failed_and_continues(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "bad")
        _insert_track(mem_conn, "good")

        call_count = [0]

        def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("network down")
            return _make_match()

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            side_effect=_side_effect,
        ):
            result = MBIdentityResolver().resolve_batch(limit=10)

        assert result.failed == 1
        assert result.resolved == 1

    def test_exception_still_stamps_enriched_at(
        self, mem_conn: sqlite3.Connection
    ) -> None:
        _insert_track(mem_conn, "bad")

        with patch(
            "oracle.enrichers.mb_identity.enrich_by_text",
            side_effect=RuntimeError("oops"),
        ):
            MBIdentityResolver().resolve_batch(limit=10)

        row = mem_conn.execute("SELECT last_enriched_at FROM tracks WHERE track_id='bad'").fetchone()
        assert row["last_enriched_at"] is not None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_empty_library(self, mem_conn: sqlite3.Connection) -> None:
        s = MBIdentityResolver().stats()
        assert s.total_active == 0
        assert s.recording_mbid_count == 0
        assert s.coverage_pct == 0.0

    def test_stats_counts_mbid_columns(self, mem_conn: sqlite3.Connection) -> None:
        _insert_track(mem_conn, "t1", recording_mbid="r1")
        _insert_track(mem_conn, "t2", recording_mbid="r2")
        _insert_track(mem_conn, "t3")  # no MBID

        mem_conn.execute("UPDATE tracks SET artist_mbid='a1' WHERE track_id='t1'")
        mem_conn.commit()

        s = MBIdentityResolver().stats()
        assert s.total_active == 3
        assert s.recording_mbid_count == 2
        assert s.artist_mbid_count == 1
        assert s.coverage_pct == pytest.approx(66.7, abs=0.1)

    def test_stats_excludes_inactive_tracks(self, mem_conn: sqlite3.Connection) -> None:
        _insert_track(mem_conn, "active1", recording_mbid="r1")
        _insert_track(mem_conn, "inactive1", recording_mbid="r2", status="inactive")

        s = MBIdentityResolver().stats()
        assert s.total_active == 1
        assert s.recording_mbid_count == 1

    def test_stats_returns_mbidstats_type(self, mem_conn: sqlite3.Connection) -> None:
        s = MBIdentityResolver().stats()
        assert isinstance(s, MBIDStats)
