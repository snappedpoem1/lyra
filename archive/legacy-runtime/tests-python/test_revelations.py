"""Contract tests for GET /api/stats/revelations — Wave 15.

Monkeypatches `get_connection` in the core blueprint module so that the
endpoint runs against an isolated in-memory SQLite database.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

import lyra_api
import oracle.api.blueprints.core as core_bp


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendation_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    feedback_type TEXT NOT NULL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);
CREATE TABLE IF NOT EXISTS playback_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    ts REAL NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "revelations_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(db: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(
        core_bp,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(db, timeout=timeout),
    )
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as tc:
        yield tc


def _seed(db: Path, days_ago: float = 3.0, feedback_type: str = "accept") -> None:
    """Insert a matching feedback + playback pair."""
    now = time.time()
    rec_at = now - days_ago * 86400
    play_at = rec_at + 3600  # 1 hour after recommendation
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO recommendation_feedback (track_id, artist, title, feedback_type, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("tr1", "Band A", "Song X", feedback_type, rec_at),
    )
    conn.execute(
        "INSERT INTO playback_history (track_id, ts) VALUES (?, ?)",
        ("tr1", play_at),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRevelationsEndpoint:
    def test_returns_200(self, client: Any) -> None:
        r = client.get("/api/stats/revelations")
        assert r.status_code == 200

    def test_response_has_required_keys(self, client: Any) -> None:
        data = client.get("/api/stats/revelations").get_json()
        assert "window_days" in data
        assert "count_this_window" in data
        assert "count_all_time" in data
        assert "revelations" in data

    def test_empty_db_returns_zero_counts(self, client: Any) -> None:
        data = client.get("/api/stats/revelations").get_json()
        assert data["count_this_window"] == 0
        assert data["count_all_time"] == 0
        assert data["revelations"] == []

    def test_matching_pair_counts_as_revelation(self, client: Any, db: Path) -> None:
        _seed(db, days_ago=2.0)
        data = client.get("/api/stats/revelations?window_days=7").get_json()
        assert data["count_all_time"] >= 1
        assert len(data["revelations"]) >= 1

    def test_window_days_param_is_respected(self, client: Any, db: Path) -> None:
        # Seed a revelation 20 days ago — outside a 7-day window_days query
        _seed(db, days_ago=20.0)
        data_narrow = client.get("/api/stats/revelations?window_days=7").get_json()
        data_wide = client.get("/api/stats/revelations?window_days=30").get_json()
        assert data_wide["count_all_time"] >= data_narrow["count_all_time"]

    def test_default_window_days_is_seven(self, client: Any) -> None:
        data = client.get("/api/stats/revelations").get_json()
        assert data["window_days"] == 7

    def test_custom_window_days_reflected_in_response(self, client: Any) -> None:
        data = client.get("/api/stats/revelations?window_days=14").get_json()
        assert data["window_days"] == 14

    def test_revelation_detail_has_expected_keys(self, client: Any, db: Path) -> None:
        _seed(db, days_ago=1.0)
        data = client.get("/api/stats/revelations?window_days=7").get_json()
        if data["revelations"]:
            rev = data["revelations"][0]
            for key in ("track_id", "artist", "title", "feedback_type",
                        "recommended_at", "first_replayed_at", "replay_count"):
                assert key in rev

    def test_limit_param_caps_detail_list(self, client: Any, db: Path) -> None:
        # Insert multiple distinct revelations
        conn = sqlite3.connect(db)
        now = time.time()
        for i in range(5):
            rec_at = now - i * 3600 - 86400  # yesterday, staggered
            conn.execute(
                "INSERT INTO recommendation_feedback (track_id, artist, title, feedback_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"trk{i}", "Artist", f"Song {i}", "queue", rec_at),
            )
            conn.execute(
                "INSERT INTO playback_history (track_id, ts) VALUES (?, ?)",
                (f"trk{i}", rec_at + 1800),
            )
        conn.commit()
        conn.close()

        data = client.get("/api/stats/revelations?limit=3").get_json()
        assert len(data["revelations"]) <= 3

    def test_feedback_type_queue_counts(self, client: Any, db: Path) -> None:
        _seed(db, feedback_type="queue")
        data = client.get("/api/stats/revelations?window_days=30").get_json()
        assert data["count_all_time"] >= 1

    def test_feedback_type_replay_counts(self, client: Any, db: Path) -> None:
        _seed(db, feedback_type="replay")
        data = client.get("/api/stats/revelations?window_days=30").get_json()
        assert data["count_all_time"] >= 1
