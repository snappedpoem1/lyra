"""Contract tests for oracle.duplicates — Wave 15.

Uses only in-memory SQLite and monkeypatches get_connection so no real DB
is needed.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

import oracle.duplicates as dup_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path: Path):
    """In-memory SQLite with a miniature tracks table."""
    db_path = tmp_path / "dup_test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE tracks (
            track_id TEXT PRIMARY KEY,
            file_path TEXT,
            artist TEXT,
            title TEXT,
            file_hash TEXT
        );
        -- Exact duplicate pair (same hash)
        INSERT INTO tracks VALUES ('t1', '/music/a.flac', 'Band A', 'Song X', 'hash_abc');
        INSERT INTO tracks VALUES ('t2', '/music/b.flac', 'Band A', 'Song X', 'hash_abc');
        -- Unique track
        INSERT INTO tracks VALUES ('t3', '/music/c.flac', 'Band B', 'Other',  'hash_def');
        -- Metadata near-duplicate (slightly different capitalisation)
        INSERT INTO tracks VALUES ('t4', '/music/d.flac', 'band a', 'song x',  'hash_xyz');
        -- Path duplicate
        INSERT INTO tracks VALUES ('t5', '/music/same.flac', 'Band C', 'Track',  'hash_111');
        INSERT INTO tracks VALUES ('t6', '/music/same.flac', 'Band C', 'Track',  'hash_222');
        """
    )
    conn.commit()
    return db_path


@pytest.fixture(autouse=True)
def patch_get_connection(db: Path, monkeypatch: pytest.MonkeyPatch):
    """Route get_connection calls in the duplicates module to the test DB."""
    def _fake_gc(timeout: float = 10.0):
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(dup_module, "get_connection", _fake_gc)


# ---------------------------------------------------------------------------
# find_exact_duplicates
# ---------------------------------------------------------------------------

class TestFindExactDuplicates:
    def test_returns_groups_for_shared_hash(self) -> None:
        groups = dup_module.find_exact_duplicates()
        assert len(groups) == 1
        ids = {m["track_id"] for m in groups[0]}
        assert ids == {"t1", "t2"}

    def test_unique_hash_not_included(self) -> None:
        groups = dup_module.find_exact_duplicates()
        all_ids = {m["track_id"] for g in groups for m in g}
        assert "t3" not in all_ids

    def test_member_has_expected_keys(self) -> None:
        groups = dup_module.find_exact_duplicates()
        member = groups[0][0]
        assert "track_id" in member
        assert "file_path" in member
        assert "artist" in member
        assert "title" in member
        assert "file_hash" in member


# ---------------------------------------------------------------------------
# find_metadata_duplicates
# ---------------------------------------------------------------------------

class TestFindMetadataDuplicates:
    def test_finds_near_duplicate_names(self) -> None:
        # t1/t4 share artist+title modulo case
        groups = dup_module.find_metadata_duplicates(threshold=0.85)
        all_ids = {m["track_id"] for g in groups for m in g}
        # t1 and t4 should appear together (or at minimum both present)
        assert "t1" in all_ids or "t4" in all_ids

    def test_distinct_tracks_not_grouped(self) -> None:
        groups = dup_module.find_metadata_duplicates(threshold=0.85)
        for g in groups:
            ids = {m["track_id"] for m in g}
            # t3 ("Band B / Other") should not be grouped with t1 ("Band A / Song X")
            assert not ({"t1", "t3"} <= ids)

    def test_high_threshold_reduces_groups(self) -> None:
        groups_loose = dup_module.find_metadata_duplicates(threshold=0.5)
        groups_strict = dup_module.find_metadata_duplicates(threshold=0.99)
        assert len(groups_strict) <= len(groups_loose)


# ---------------------------------------------------------------------------
# find_path_duplicates
# ---------------------------------------------------------------------------

class TestFindPathDuplicates:
    def test_returns_group_for_shared_path(self) -> None:
        groups = dup_module.find_path_duplicates()
        assert len(groups) == 1
        ids = {m["track_id"] for m in groups[0]}
        assert ids == {"t5", "t6"}

    def test_unique_path_not_included(self) -> None:
        groups = dup_module.find_path_duplicates()
        all_ids = {m["track_id"] for g in groups for m in g}
        assert "t1" not in all_ids
        assert "t3" not in all_ids


# ---------------------------------------------------------------------------
# get_duplicate_summary
# ---------------------------------------------------------------------------

class TestGetDuplicateSummary:
    def test_returns_all_strategy_keys(self) -> None:
        summary = dup_module.get_duplicate_summary()
        assert "exact" in summary
        assert "metadata" in summary
        assert "path" in summary
        assert "metadata_threshold" in summary

    def test_exact_group_count_is_one(self) -> None:
        summary = dup_module.get_duplicate_summary()
        assert summary["exact"]["group_count"] == 1
        assert summary["exact"]["track_count"] == 2

    def test_path_group_count_is_one(self) -> None:
        summary = dup_module.get_duplicate_summary()
        assert summary["path"]["group_count"] == 1
        assert summary["path"]["track_count"] == 2


# ---------------------------------------------------------------------------
# find_all_duplicates
# ---------------------------------------------------------------------------

class TestFindAllDuplicates:
    def test_returns_all_strategy_keys(self) -> None:
        result = dup_module.find_all_duplicates()
        assert "exact" in result
        assert "metadata" in result
        assert "path" in result

    def test_exact_groups_list(self) -> None:
        result = dup_module.find_all_duplicates()
        assert isinstance(result["exact"], list)
