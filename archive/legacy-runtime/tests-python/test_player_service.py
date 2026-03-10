from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pytest

import oracle.player.repository as player_repo_module
from oracle.player.repository import PlayerRepository
from oracle.player.service import PlayerService


class FakePlaybackEngine:
    def __init__(self) -> None:
        self.play_calls: list[dict[str, Any]] = []
        self.pause_calls = 0
        self.resume_calls = 0
        self.seek_calls: list[int] = []
        self.stop_calls = 0
        self.closed = False
        self._position_ms = 0
        self._finished = False
        self._available = True

    @property
    def is_available(self) -> bool:
        return self._available

    def play(
        self,
        filepath: Path,
        *,
        start_position_ms: int = 0,
        volume: float = 0.82,
        muted: bool = False,
    ) -> int | None:
        self.play_calls.append(
            {
                "filepath": str(filepath),
                "start_position_ms": start_position_ms,
                "volume": volume,
                "muted": muted,
            }
        )
        self._position_ms = start_position_ms
        self._finished = False
        return 180000

    def resume(self) -> None:
        self.resume_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def seek(self, position_ms: int) -> None:
        self.seek_calls.append(position_ms)
        self._position_ms = position_ms

    def stop(self) -> None:
        self.stop_calls += 1
        self._finished = False

    def set_volume(self, volume: float) -> None:
        return None

    def set_muted(self, muted: bool) -> None:
        return None

    def position_ms(self) -> int | None:
        return self._position_ms

    def is_finished(self) -> bool:
        return self._finished

    def close(self) -> None:
        self.closed = True


def _make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[PlayerRepository, Path]:
    db_path = tmp_path / "player_test.db"

    def _connect(timeout: float = 10.0) -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), timeout=timeout)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    monkeypatch.setattr(player_repo_module, "get_connection", _connect)
    repo = PlayerRepository()
    repo.ensure_tables()

    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                album TEXT,
                duration REAL,
                filepath TEXT
            )
            """
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO tracks (track_id, artist, title, album, duration, filepath) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("t1", "Artist 1", "Song 1", "Album 1", 200.0, "C:/music/1.flac"),
                ("t2", "Artist 2", "Song 2", "Album 2", 180.0, "C:/music/2.flac"),
                ("t3", "Artist 3", "Song 3", "Album 3", 240.0, "C:/music/3.flac"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return repo, db_path


def test_player_queue_mutation_and_navigation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _make_repo(tmp_path, monkeypatch)
    engine = FakePlaybackEngine()
    service = PlayerService(repository=repo, playback_engine=engine)
    try:
        service.add_to_queue("t1")
        service.add_to_queue("t2")
        service.add_to_queue("t3")
        queue = service.get_queue()
        assert queue["count"] == 3
        assert [item["track_id"] for item in queue["items"]] == ["t1", "t2", "t3"]

        service.reorder_queue(["t3", "t1", "t2"])
        reordered = service.get_queue()
        assert [item["track_id"] for item in reordered["items"]] == ["t3", "t1", "t2"]

        state = service.play(queue_index=0)
        assert state["current_track"]["track_id"] == "t3"
        assert engine.play_calls
        state = service.next_track()
        assert state["current_track"]["track_id"] == "t1"
        state = service.previous_track()
        assert state["current_track"]["track_id"] == "t3"
    finally:
        service.close()
    assert engine.closed is True


def test_repeat_modes_and_shuffle_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _make_repo(tmp_path, monkeypatch)
    engine = FakePlaybackEngine()
    service = PlayerService(repository=repo, playback_engine=engine)
    try:
        service.add_to_queue("t1")
        service.add_to_queue("t2")
        service.add_to_queue("t3")

        service.play(queue_index=1)
        service.set_mode(repeat_mode="one")
        state = service.next_track()
        assert state["current_track"]["track_id"] == "t2"

        service.set_mode(repeat_mode="all")
        service.play(queue_index=2)
        wrapped = service.next_track()
        assert wrapped["current_track"]["track_id"] == "t1"

        service.set_mode(shuffle=True)
        first_shuffle = [item["track_id"] for item in service.get_queue()["items"]]
        service.set_mode(shuffle=False)
        service.set_mode(shuffle=True)
        second_shuffle = [item["track_id"] for item in service.get_queue()["items"]]
        assert first_shuffle == second_shuffle
    finally:
        service.close()


def test_restore_from_db_on_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _make_repo(tmp_path, monkeypatch)
    engine_a = FakePlaybackEngine()
    service = PlayerService(repository=repo, playback_engine=engine_a)
    try:
        service.add_to_queue("t1")
        service.add_to_queue("t2")
        service.play(queue_index=1)
        service.seek(15000)
        service.pause()
    finally:
        service.close()

    engine_b = FakePlaybackEngine()
    restored = PlayerService(repository=repo, playback_engine=engine_b)
    try:
        queue = restored.get_queue()
        state = restored.get_state()
        assert [item["track_id"] for item in queue["items"]] == ["t1", "t2"]
        assert state["current_track"]["track_id"] == "t2"
        assert state["position_ms"] == 15000
        assert state["status"] == "paused"
    finally:
        restored.close()


def test_pause_seek_resume_call_playback_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _make_repo(tmp_path, monkeypatch)
    engine = FakePlaybackEngine()
    service = PlayerService(repository=repo, playback_engine=engine)
    try:
        service.add_to_queue("t1")
        service.play(queue_index=0)
        service.pause()
        service.seek(42000)
        service.play()
        assert engine.pause_calls == 1
        assert engine.seek_calls[-1] == 42000
        assert engine.resume_calls == 1
    finally:
        service.close()
