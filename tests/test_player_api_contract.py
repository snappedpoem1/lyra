from __future__ import annotations

from queue import Queue
from typing import Any

import pytest

import lyra_api
import oracle.api.blueprints.player as player_bp


class _FakePlayerService:
    def __init__(self, *, engine_available: bool = True) -> None:
        self.engine_available = engine_available
        self._subscription: Queue[dict[str, Any]] = Queue()

    def get_state(self) -> dict[str, Any]:
        return {
            "status": "paused",
            "current_track": {
                "track_id": "track-1",
                "artist": "Artist",
                "title": "Title",
                "album": "Album",
                "duration_ms": 123000,
                "filepath": "C:/music/track.flac",
            },
            "position_ms": 1000,
            "duration_ms": 123000,
            "volume": 0.82,
            "muted": False,
            "shuffle": False,
            "repeat_mode": "off",
            "updated_at": 1.0,
            "current_queue_index": 0,
        }

    def get_queue(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "track_id": "track-1",
                    "artist": "Artist",
                    "title": "Title",
                    "album": "Album",
                    "duration_ms": 123000,
                    "filepath": "C:/music/track.flac",
                }
            ],
            "current_index": 0,
            "count": 1,
        }

    def play(self, track_id: str | None = None, queue_index: int | None = None) -> dict[str, Any]:
        if track_id == "missing":
            raise KeyError("track not found")
        if queue_index is not None and queue_index < 0:
            raise IndexError("queue_index out of range")
        return self.get_state()

    def pause(self) -> dict[str, Any]:
        raise RuntimeError("Cannot pause when player is not playing")

    def seek(self, position_ms: int) -> dict[str, Any]:
        return self.get_state() | {"position_ms": position_ms}

    def next_track(self) -> dict[str, Any]:
        return self.get_state()

    def previous_track(self) -> dict[str, Any]:
        return self.get_state()

    def add_to_queue(self, track_id: str, at_index: int | None = None) -> dict[str, Any]:
        if track_id == "missing":
            raise KeyError("track not found")
        return self.get_queue()

    def reorder_queue(self, ordered_track_ids: list[str]) -> dict[str, Any]:
        if not ordered_track_ids:
            raise ValueError("ordered_track_ids must include every queued track exactly once")
        return self.get_queue()

    def set_mode(self, *, shuffle: bool | None = None, repeat_mode: str | None = None) -> dict[str, Any]:
        if repeat_mode == "invalid":
            raise ValueError("repeat_mode must be one of off|one|all")
        return self.get_state() | {"shuffle": bool(shuffle) if shuffle is not None else False}

    def subscribe(self) -> Queue[dict[str, Any]]:
        return self._subscription

    def unsubscribe(self, queue: Queue[dict[str, Any]]) -> None:
        return None

    def publish_error(self, message: str) -> None:
        return None


@pytest.fixture
def client():
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as test_client:
        yield test_client


def test_player_state_contract(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.get("/api/player/state")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "paused"
    assert payload["current_track"]["track_id"] == "track-1"
    assert "position_ms" in payload
    assert "repeat_mode" in payload


def test_player_play_error_semantics(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_bp, "get_player_service", lambda: _FakePlayerService())

    invalid = client.post("/api/player/play", json={"queue_index": "bad"})
    assert invalid.status_code == 400

    missing = client.post("/api/player/play", json={"track_id": "missing"})
    assert missing.status_code == 404


def test_player_transition_conflict(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.post("/api/player/pause", json={})
    assert response.status_code == 409


def test_player_unavailable_returns_503(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_bp, "get_player_service", lambda: _FakePlayerService(engine_available=False))
    response = client.post("/api/player/play", json={"track_id": "track-1"})
    assert response.status_code == 503


def test_player_event_stream_contract(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_bp, "get_player_service", lambda: _FakePlayerService())
    response = client.get("/ws/player", buffered=False)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    iterator = response.response
    first = next(iterator)
    assert b"player_state_changed" in first
