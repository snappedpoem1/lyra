from __future__ import annotations

from typing import Any

import pytest
import sqlite3
from pathlib import Path

import lyra_api
import oracle.api.blueprints.oracle_actions as oracle_actions_bp


class _FakePlayerService:
    def __init__(self) -> None:
        self.engine_available = True
        self.queued_ids: list[str] = []

    def get_state(self) -> dict[str, Any]:
        return {
            "status": "paused",
            "current_track": {
                "track_id": "t1",
                "artist": "Artist 1",
                "title": "Song 1",
                "album": "Album 1",
                "duration_ms": 180000,
                "filepath": "C:/music/1.flac",
            },
            "position_ms": 0,
            "duration_ms": 180000,
            "volume": 0.82,
            "muted": False,
            "shuffle": False,
            "repeat_mode": "off",
            "updated_at": 1.0,
            "current_queue_index": 0,
        }

    def get_queue(self) -> dict[str, Any]:
        return {"items": [], "current_index": 0, "count": len(self.queued_ids)}

    def add_to_queue(self, track_id: str, at_index: int | None = None) -> dict[str, Any]:
        del at_index
        self.queued_ids.append(track_id)
        return {"items": [{"track_id": x} for x in self.queued_ids], "current_index": 0, "count": len(self.queued_ids)}

    def play(self, track_id: str | None = None, queue_index: int | None = None) -> dict[str, Any]:
        del track_id, queue_index
        return self.get_state()

    def pause(self) -> dict[str, Any]:
        return self.get_state()

    def next_track(self) -> dict[str, Any]:
        return self.get_state()

    def previous_track(self) -> dict[str, Any]:
        return self.get_state()

    def publish_error(self, message: str) -> None:
        del message
        return None

    def set_volume(self, volume: float) -> dict[str, Any]:
        if volume < 0.0 or volume > 1.0:
            raise ValueError("volume must be between 0.0 and 1.0")
        state = self.get_state()
        state["volume"] = volume
        return state

    def set_mode(
        self,
        shuffle: bool | None = None,
        repeat_mode: str | None = None,
    ) -> dict[str, Any]:
        state = self.get_state()
        if shuffle is not None:
            state["shuffle"] = shuffle
        if repeat_mode is not None:
            state["repeat_mode"] = repeat_mode
        return state

    def clear_queue(self) -> dict[str, Any]:
        self.queued_ids = []
        state = self.get_state()
        state["status"] = "idle"
        return state


@pytest.fixture
def client() -> Any:
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as test_client:
        yield test_client


def test_oracle_chat_requires_message(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post("/api/oracle/chat", json={})
    assert response.status_code == 400


def test_oracle_action_queue_tracks_dedupes(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "queue_tracks", "payload": {"track_ids": ["t2", "t2", "t3", ""]}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["queued_count"] == 2
    assert payload["queued_track_ids"] == ["t2", "t3"]


def test_oracle_action_start_vibe_routes_to_executor(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "_execute_start_vibe",
        lambda _service, _payload: {
            "status": "ok",
            "action_type": "start_vibe",
            "queued_count": 3,
            "missing_paths": [],
            "queue": {"count": 3},
        },
    )
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "start_vibe", "payload": {"prompt": "dreamy night drive"}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["action_type"] == "start_vibe"
    assert payload["queued_count"] == 3


def test_oracle_action_start_playlust_routes_to_executor(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "_execute_start_playlust",
        lambda _service, _payload: {
            "status": "ok",
            "action_type": "start_playlust",
            "queued_count": 8,
            "missing_paths": [],
            "queue": {"count": 8},
        },
    )
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "start_playlust", "payload": {"mood": "euphoric sunrise", "duration_minutes": 45}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["action_type"] == "start_playlust"
    assert payload["queued_count"] == 8


def test_oracle_action_switch_chaos_intensity_queue_now(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "_run_chaos_selection",
        lambda current_track_id, count: [{"track_id": "cx1"}, {"track_id": "cx2"}][:count],
    )
    response = client.post(
        "/api/oracle/action/execute",
        json={
            "action_type": "switch_chaos_intensity",
            "payload": {"intensity": "high", "queue_now": True},
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["chaos_intensity"] == pytest.approx(0.85)
    assert payload["queued_now"] is True
    assert payload["queued_track_ids"]


def test_oracle_action_switch_chaos_intensity_rejects_invalid(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "switch_chaos_intensity", "payload": {"intensity": "warp"}},
    )
    assert response.status_code == 400


def test_oracle_action_request_acquisition_queues_lead(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "oracle-actions.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                status TEXT,
                updated_at REAL,
                created_at REAL,
                added_at REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE acquisition_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                priority_score REAL DEFAULT 0.0,
                source TEXT,
                search_query TEXT,
                playlist_name TEXT,
                status TEXT DEFAULT 'pending',
                added_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    monkeypatch.setattr(oracle_actions_bp, "get_write_mode", lambda: "apply_allowed")
    monkeypatch.setattr(
        oracle_actions_bp,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(db_path, timeout=timeout),
    )

    response = client.post(
        "/api/oracle/action/execute",
        json={
            "action_type": "request_acquisition",
            "payload": {
                "artist": "Future Artist",
                "title": "Future Song",
                "provider": "listenbrainz",
                "score": 0.42,
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "queued"
    assert payload["inserted"] is True

    verify = sqlite3.connect(db_path)
    try:
        row = verify.execute(
            "SELECT artist, title, source, status FROM acquisition_queue"
        ).fetchone()
    finally:
        verify.close()

    assert row == ("Future Artist", "Future Song", "oracle_broker:listenbrainz", "pending")


# ---------------------------------------------------------------------------
# Wave 12 — new action breadth tests
# ---------------------------------------------------------------------------

def test_oracle_action_resume(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "resume"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["action_type"] == "resume"


def test_oracle_action_set_volume(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "set_volume", "payload": {"volume": 0.5}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]["volume"] == pytest.approx(0.5)


def test_oracle_action_set_volume_missing_payload(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "set_volume"},
    )
    assert response.status_code == 400


def test_oracle_action_set_shuffle(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "set_shuffle", "payload": {"shuffle": True}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]["shuffle"] is True


def test_oracle_action_set_repeat(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "set_repeat", "payload": {"mode": "one"}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]["repeat_mode"] == "one"


def test_oracle_action_clear_queue(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakePlayerService()
    service.queued_ids = ["x1", "x2"]
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "clear_queue"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert service.queued_ids == []


def test_oracle_action_play_artist(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pa.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                album TEXT,
                track_number INTEGER,
                status TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO tracks VALUES (?,?,?,?,?,?)",
            [
                ("t10", "The Cure", "Close to Me", "The Head on the Door", 1, "active"),
                ("t11", "The Cure", "In Between Days", "The Head on the Door", 2, "active"),
                ("t12", "Other Artist", "Random Song", "Other Album", 1, "active"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(db_path, timeout=timeout),
    )

    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "play_artist", "payload": {"artist": "The Cure"}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["artist"] == "The Cure"
    assert set(service.queued_ids) == {"t10", "t11"}


def test_oracle_action_play_artist_missing_artist(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "play_artist"},
    )
    assert response.status_code == 400


def test_oracle_action_play_album(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pal.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                album TEXT,
                track_number INTEGER,
                status TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO tracks VALUES (?,?,?,?,?,?)",
            [
                ("a1", "Portishead", "Sour Times", "Dummy", 1, "active"),
                ("a2", "Portishead", "Glory Box", "Dummy", 2, "active"),
                ("a3", "Portishead", "Other Album", "Roseland NYC Live", 1, "active"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(db_path, timeout=timeout),
    )

    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "play_album", "payload": {"album": "Dummy", "artist": "Portishead"}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert set(service.queued_ids) == {"a1", "a2"}


def test_oracle_action_play_similar(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "psim.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY, status TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE similar (
                source_track_id TEXT,
                target_track_id TEXT,
                score REAL
            )"""
        )
        conn.executemany("INSERT INTO tracks VALUES (?,?)", [("s1", "active"), ("s2", "active")])
        conn.executemany(
            "INSERT INTO similar VALUES (?,?,?)",
            [("t1", "s1", 0.9), ("t1", "s2", 0.85)],
        )
        conn.commit()
    finally:
        conn.close()

    service = _FakePlayerService()
    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: service)
    monkeypatch.setattr(
        oracle_actions_bp,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(db_path, timeout=timeout),
    )

    # _FakePlayerService.get_state() returns current_track.track_id == "t1"
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "play_similar"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["source_track_id"] == "t1"
    assert set(service.queued_ids) == {"s1", "s2"}


def test_oracle_action_play_similar_no_current_track(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _IdleFake(_FakePlayerService):
        def get_state(self) -> dict[str, Any]:
            state = super().get_state()
            state["current_track"] = None
            return state

    monkeypatch.setattr(oracle_actions_bp, "get_player_service", lambda: _IdleFake())
    response = client.post(
        "/api/oracle/action/execute",
        json={"action_type": "play_similar"},
    )
    assert response.status_code == 409
