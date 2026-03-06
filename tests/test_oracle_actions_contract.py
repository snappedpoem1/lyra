from __future__ import annotations

from typing import Any

import pytest

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
