"""Canonical backend player service."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from queue import Queue
from threading import RLock, Thread
import sqlite3
import time
from typing import Any

from oracle.player.audio_engine import PlaybackEngine, create_playback_engine
from oracle.player.events import PlayerEventBus
from oracle.player.repository import PlayerRepository

logger = logging.getLogger(__name__)

VALID_REPEAT_MODES = {"off", "one", "all"}
PLAYER_TICK_SECONDS = 1.0


class PlayerService:
    """In-process player state machine with persisted queue/state."""

    def __init__(
        self,
        repository: PlayerRepository | None = None,
        playback_engine: PlaybackEngine | None = None,
    ) -> None:
        self._repository = repository or PlayerRepository()
        self._repository.ensure_tables()
        self._playback_engine = playback_engine or create_playback_engine()
        self._events = PlayerEventBus()
        self._lock = RLock()

        state = self._repository.load_state()
        self._status: str = str(state["status"])
        self._current_track_id: str | None = state["current_track_id"]
        self._current_queue_index: int = int(state["current_queue_index"])
        self._position_ms: int = int(state["position_ms"])
        self._duration_ms: int = int(state["duration_ms"])
        self._volume: float = float(state["volume"])
        self._muted: bool = bool(state["muted"])
        self._shuffle: bool = bool(state["shuffle"])
        self._repeat_mode: str = str(state["repeat_mode"])
        self._updated_at: float = float(state["updated_at"])
        self._queue_track_ids: list[str] = self._repository.load_queue()
        self._linear_queue_track_ids: list[str] = list(self._queue_track_ids)
        self._last_tick_at: float = time.time()
        self._shutdown = False
        self._engine_available = os.getenv("LYRA_PLAYER_DISABLED", "0").strip().lower() not in {
            "1",
            "true",
            "yes",
        }

        self._coerce_loaded_state()
        self._ticker = Thread(target=self._run_ticker, name="player-service-ticker", daemon=True)
        self._ticker.start()

    @property
    def engine_available(self) -> bool:
        """Whether the player engine is available for transport commands."""
        return self._engine_available

    def subscribe(self) -> Queue[dict[str, Any]]:
        """Subscribe to player event envelope stream."""
        return self._events.subscribe()

    def close(self) -> None:
        """Stop background ticker thread."""
        self._shutdown = True
        if self._ticker.is_alive():
            self._ticker.join(timeout=2.0)
        self._playback_engine.close()

    def unsubscribe(self, queue: Queue[dict[str, Any]]) -> None:
        """Unsubscribe from player event stream."""
        self._events.unsubscribe(queue)

    def get_state(self) -> dict[str, Any]:
        """Return canonical player state response payload."""
        with self._lock:
            return self._state_payload_unlocked()

    def get_queue(self) -> dict[str, Any]:
        """Return canonical queue response payload."""
        with self._lock:
            return self._queue_payload_unlocked()

    def play(self, track_id: str | None = None, queue_index: int | None = None) -> dict[str, Any]:
        """Play/resume by track id, queue index, or current track."""
        with self._lock:
            self._require_engine()
            current_id = self._current_track_id
            if queue_index is not None:
                if queue_index < 0 or queue_index >= len(self._queue_track_ids):
                    raise IndexError("queue_index out of range")
                self._current_queue_index = queue_index
                track_id = self._queue_track_ids[queue_index]
            elif track_id:
                if not self._repository.get_track(track_id):
                    raise KeyError(f"track not found: {track_id}")
                if track_id in self._queue_track_ids:
                    self._current_queue_index = self._queue_track_ids.index(track_id)
                else:
                    self._queue_track_ids.append(track_id)
                    self._linear_queue_track_ids.append(track_id)
                    self._current_queue_index = len(self._queue_track_ids) - 1
                    self._persist_queue_unlocked()
                    self._emit_queue_changed_unlocked()
            elif self._current_track_id:
                track_id = self._current_track_id
            elif self._queue_track_ids:
                self._current_queue_index = min(self._current_queue_index, len(self._queue_track_ids) - 1)
                track_id = self._queue_track_ids[self._current_queue_index]
            else:
                raise ValueError("No track selected")

            if not track_id:
                raise ValueError("No track selected")

            if current_id and current_id != track_id:
                self._record_playback_if_meaningful_unlocked(track_id=current_id, context="player_switch")
            if self._status == "paused" and current_id == track_id:
                try:
                    self._playback_engine.resume()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("audio resume failed for %s: %s", track_id, exc)
                self._status = "playing"
                self._touch_state_unlocked()
                self._persist_state_unlocked()
                self._emit_state_changed_unlocked()
                return self._state_payload_unlocked()

            self._start_track_unlocked(track_id=track_id, start_position_ms=0)
            return self._state_payload_unlocked()

    def pause(self) -> dict[str, Any]:
        """Pause currently playing track."""
        with self._lock:
            self._require_engine()
            if self._status != "playing":
                raise RuntimeError("Cannot pause when player is not playing")
            try:
                self._playback_engine.pause()
            except Exception as exc:  # noqa: BLE001
                logger.warning("audio pause failed: %s", exc)
            self._status = "paused"
            self._touch_state_unlocked()
            self._persist_state_unlocked()
            self._emit_state_changed_unlocked()
            return self._state_payload_unlocked()

    def seek(self, position_ms: int) -> dict[str, Any]:
        """Seek within the active track."""
        with self._lock:
            self._require_engine()
            if not self._current_track_id:
                raise RuntimeError("Cannot seek when no track is loaded")
            if position_ms < 0:
                raise ValueError("position_ms must be >= 0")
            clamped = min(position_ms, self._duration_ms) if self._duration_ms > 0 else position_ms
            self._position_ms = int(clamped)
            try:
                self._playback_engine.seek(self._position_ms)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audio seek failed: %s", exc)
            self._touch_state_unlocked()
            self._persist_state_unlocked()
            self._emit_state_changed_unlocked()
            return self._state_payload_unlocked()

    def next_track(self) -> dict[str, Any]:
        """Move to next track respecting repeat mode."""
        with self._lock:
            self._require_engine()
            if not self._queue_track_ids:
                raise RuntimeError("Queue is empty")
            if self._current_track_id:
                self._record_playback_if_meaningful_unlocked(
                    track_id=self._current_track_id,
                    context="player_next",
                )

            if self._repeat_mode == "one" and self._current_track_id:
                self._start_track_unlocked(track_id=self._current_track_id, start_position_ms=0)
                return self._state_payload_unlocked()

            target_index = self._current_queue_index + 1
            if target_index >= len(self._queue_track_ids):
                if self._repeat_mode == "all":
                    target_index = 0
                else:
                    self._status = "ended"
                    self._position_ms = self._duration_ms
                    self._touch_state_unlocked()
                    self._persist_state_unlocked()
                    self._emit_track_finished_unlocked(self._current_track_id)
                    self._emit_state_changed_unlocked()
                    return self._state_payload_unlocked()

            self._current_queue_index = target_index
            next_track_id = self._queue_track_ids[self._current_queue_index]
            self._start_track_unlocked(track_id=next_track_id, start_position_ms=0)
            return self._state_payload_unlocked()

    def previous_track(self) -> dict[str, Any]:
        """Move to previous track or restart current track when near beginning."""
        with self._lock:
            self._require_engine()
            if not self._queue_track_ids:
                raise RuntimeError("Queue is empty")
            if self._position_ms > 5000 and self._current_track_id:
                self._position_ms = 0
                self._touch_state_unlocked()
                self._persist_state_unlocked()
                self._emit_state_changed_unlocked()
                return self._state_payload_unlocked()

            target_index = self._current_queue_index - 1
            if target_index < 0:
                if self._repeat_mode == "all":
                    target_index = len(self._queue_track_ids) - 1
                else:
                    target_index = 0
            self._current_queue_index = target_index
            track_id = self._queue_track_ids[self._current_queue_index]
            self._start_track_unlocked(track_id=track_id, start_position_ms=0)
            return self._state_payload_unlocked()

    def add_to_queue(self, track_id: str, at_index: int | None = None) -> dict[str, Any]:
        """Add one track to queue."""
        with self._lock:
            if not self._repository.get_track(track_id):
                raise KeyError(f"track not found: {track_id}")
            insert_at = at_index if at_index is not None else len(self._queue_track_ids)
            if insert_at < 0 or insert_at > len(self._queue_track_ids):
                raise ValueError("at_index out of range")
            self._queue_track_ids.insert(insert_at, track_id)
            self._linear_queue_track_ids.insert(insert_at, track_id)
            if insert_at <= self._current_queue_index and self._queue_track_ids:
                self._current_queue_index += 1
            self._touch_state_unlocked()
            self._persist_queue_unlocked()
            self._persist_state_unlocked()
            self._emit_queue_changed_unlocked()
            self._emit_state_changed_unlocked()
            return self._queue_payload_unlocked()

    def reorder_queue(self, ordered_track_ids: list[str]) -> dict[str, Any]:
        """Replace queue ordering using a full ordered list."""
        with self._lock:
            if len(ordered_track_ids) != len(self._queue_track_ids):
                raise ValueError("ordered_track_ids must include every queued track exactly once")
            if sorted(ordered_track_ids) != sorted(self._queue_track_ids):
                raise ValueError("ordered_track_ids must include every queued track exactly once")
            self._queue_track_ids = list(ordered_track_ids)
            self._linear_queue_track_ids = list(ordered_track_ids)
            if self._current_track_id and self._current_track_id in self._queue_track_ids:
                self._current_queue_index = self._queue_track_ids.index(self._current_track_id)
            else:
                self._current_queue_index = 0
            self._touch_state_unlocked()
            self._persist_queue_unlocked()
            self._persist_state_unlocked()
            self._emit_queue_changed_unlocked()
            self._emit_state_changed_unlocked()
            return self._queue_payload_unlocked()

    def set_mode(self, *, shuffle: bool | None = None, repeat_mode: str | None = None) -> dict[str, Any]:
        """Update shuffle/repeat settings."""
        with self._lock:
            if repeat_mode is not None and repeat_mode not in VALID_REPEAT_MODES:
                raise ValueError("repeat_mode must be one of off|one|all")
            if repeat_mode is not None:
                self._repeat_mode = repeat_mode
            if shuffle is not None and shuffle != self._shuffle:
                self._shuffle = shuffle
                if self._shuffle:
                    self._queue_track_ids = self._deterministic_shuffle(self._queue_track_ids)
                else:
                    self._queue_track_ids = list(self._linear_queue_track_ids)
                if self._current_track_id and self._current_track_id in self._queue_track_ids:
                    self._current_queue_index = self._queue_track_ids.index(self._current_track_id)
                elif self._queue_track_ids:
                    self._current_queue_index = min(self._current_queue_index, len(self._queue_track_ids) - 1)
            self._touch_state_unlocked()
            self._persist_state_unlocked()
            self._persist_queue_unlocked()
            self._emit_queue_changed_unlocked()
            self._emit_state_changed_unlocked()
            return self._state_payload_unlocked()

    def set_volume(self, volume: float) -> dict[str, Any]:
        """Set playback volume (0.0–1.0)."""
        with self._lock:
            if volume < 0.0 or volume > 1.0:
                raise ValueError("volume must be between 0.0 and 1.0")
            self._volume = float(volume)
            try:
                self._playback_engine.set_volume(self._volume)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audio set_volume failed: %s", exc)
            self._touch_state_unlocked()
            self._persist_state_unlocked()
            self._emit_state_changed_unlocked()
            return self._state_payload_unlocked()

    def clear_queue(self) -> dict[str, Any]:
        """Remove all tracks from the queue and stop playback."""
        with self._lock:
            if self._current_track_id:
                try:
                    self._playback_engine.stop()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("audio stop failed during clear_queue: %s", exc)
            self._queue_track_ids = []
            self._linear_queue_track_ids = []
            self._current_track_id = None
            self._current_queue_index = 0
            self._position_ms = 0
            self._duration_ms = 0
            self._status = "idle"
            self._touch_state_unlocked()
            self._persist_state_unlocked()
            self._persist_queue_unlocked()
            self._emit_queue_changed_unlocked()
            self._emit_state_changed_unlocked()
            return self._state_payload_unlocked()

    def _coerce_loaded_state(self) -> None:
        if self._status == "playing":
            self._status = "paused"
        if self._repeat_mode not in VALID_REPEAT_MODES:
            self._repeat_mode = "off"
        if not self._queue_track_ids:
            self._current_queue_index = 0
        else:
            self._current_queue_index = max(0, min(self._current_queue_index, len(self._queue_track_ids) - 1))
            if not self._current_track_id:
                self._current_track_id = self._queue_track_ids[self._current_queue_index]
        if self._current_track_id:
            track = self._repository.get_track(self._current_track_id)
            if track:
                self._duration_ms = int(track.get("duration_ms", 0) or 0)
            else:
                self._current_track_id = None
                self._status = "idle"
                self._position_ms = 0
                self._duration_ms = 0

    def _require_engine(self) -> None:
        if not self._engine_available:
            raise PermissionError("player engine unavailable")

    def _start_track_unlocked(self, *, track_id: str, start_position_ms: int = 0) -> None:
        track = self._repository.get_track(track_id)
        if not track:
            raise KeyError(f"track not found: {track_id}")
        filepath_value = str(track.get("filepath") or "").strip()
        if not filepath_value:
            raise RuntimeError(f"track has no file path: {track_id}")
        filepath = Path(filepath_value)

        engine_duration_ms: int | None = None
        try:
            engine_duration_ms = self._playback_engine.play(
                filepath,
                start_position_ms=start_position_ms,
                volume=self._volume,
                muted=self._muted,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("audio start failed for %s (%s): %s", track_id, filepath, exc)
            engine_duration_ms = None

        self._current_track_id = track_id
        if track_id in self._queue_track_ids:
            self._current_queue_index = self._queue_track_ids.index(track_id)
        if engine_duration_ms and engine_duration_ms > 0:
            self._duration_ms = int(engine_duration_ms)
        else:
            self._duration_ms = int(track.get("duration_ms", 0) or 0)
        self._position_ms = min(max(0, int(start_position_ms)), self._duration_ms or int(start_position_ms))
        self._status = "playing"
        self._touch_state_unlocked()
        self._persist_state_unlocked()
        self._emit_track_started_unlocked(track_id)
        self._emit_state_changed_unlocked()

    def _persist_state_unlocked(self) -> None:
        self._repository.save_state(
            status=self._status,
            current_track_id=self._current_track_id,
            current_queue_index=self._current_queue_index,
            position_ms=self._position_ms,
            duration_ms=self._duration_ms,
            volume=self._volume,
            muted=self._muted,
            shuffle=self._shuffle,
            repeat_mode=self._repeat_mode,
            updated_at=self._updated_at,
        )

    def _persist_queue_unlocked(self) -> None:
        self._repository.save_queue(self._queue_track_ids)

    def _touch_state_unlocked(self) -> None:
        self._updated_at = time.time()
        self._last_tick_at = self._updated_at

    def _run_ticker(self) -> None:
        while not self._shutdown:
            time.sleep(PLAYER_TICK_SECONDS)
            try:
                with self._lock:
                    now = time.time()
                    elapsed_ms = max(0, int((now - self._last_tick_at) * 1000))
                    self._last_tick_at = now
                    if self._status != "playing" or not self._current_track_id:
                        continue
                    engine_position = self._playback_engine.position_ms()
                    if engine_position is not None and engine_position >= 0:
                        self._position_ms = int(engine_position)
                    elif elapsed_ms > 0:
                        self._position_ms += elapsed_ms

                    if self._playback_engine.is_finished():
                        if self._duration_ms > 0:
                            self._position_ms = self._duration_ms
                        self._handle_track_completion_unlocked()
                        continue

                    if self._duration_ms > 0 and self._position_ms >= self._duration_ms:
                        self._position_ms = self._duration_ms
                        self._handle_track_completion_unlocked()
                    else:
                        self._touch_state_unlocked()
                        self._persist_state_unlocked()
                        self._emit_position_tick_unlocked()
            except sqlite3.OperationalError as exc:
                logger.debug("player ticker persistence skipped: %s", exc)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("player ticker loop failed: %s", exc)
                continue

    def _handle_track_completion_unlocked(self) -> None:
        completed_track_id = self._current_track_id
        if completed_track_id:
            self._repository.record_playback(
                track_id=completed_track_id,
                context="player_complete",
                skipped=False,
                completion_rate=1.0,
            )
            self._update_taste_from_playback(completed_track_id, positive=True, weight=1.0)
        self._emit_track_finished_unlocked(completed_track_id)

        if self._repeat_mode == "one" and completed_track_id:
            self._start_track_unlocked(track_id=completed_track_id, start_position_ms=0)
            return

        next_index = self._current_queue_index + 1
        if next_index < len(self._queue_track_ids):
            self._current_queue_index = next_index
            next_track_id = self._queue_track_ids[next_index]
            self._start_track_unlocked(track_id=next_track_id, start_position_ms=0)
            return

        if self._repeat_mode == "all" and self._queue_track_ids:
            self._current_queue_index = 0
            self._start_track_unlocked(track_id=self._queue_track_ids[0], start_position_ms=0)
            return

        try:
            self._playback_engine.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug("audio stop failed at queue end: %s", exc)
        self._status = "ended"
        self._touch_state_unlocked()
        self._persist_state_unlocked()
        self._emit_state_changed_unlocked()

    def _record_playback_if_meaningful_unlocked(self, *, track_id: str, context: str) -> None:
        duration_ms = max(0, self._duration_ms)
        completion_rate = 0.0
        if duration_ms > 0:
            completion_rate = min(max(self._position_ms / duration_ms, 0.0), 1.0)
        if self._position_ms < 30000 and completion_rate < 0.25:
            return
        skipped = completion_rate < 0.3
        self._repository.record_playback(
            track_id=track_id,
            context=context,
            skipped=skipped,
            completion_rate=completion_rate,
        )
        self._update_taste_from_playback(
            track_id,
            positive=not skipped and completion_rate >= 0.8,
            weight=max(0.1, completion_rate),
        )

    def _update_taste_from_playback(self, track_id: str, *, positive: bool, weight: float) -> None:
        try:
            from oracle.taste import update_taste_from_playback

            update_taste_from_playback(track_id, positive=positive, weight=weight)
        except Exception as exc:  # noqa: BLE001
            logger.debug("taste update hook failed for %s: %s", track_id, exc)

    def _build_event_unlocked(
        self,
        *,
        event_type: str,
        include_state: bool = False,
        include_queue: bool = False,
        track_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": event_type,
            "ts": time.time(),
        }
        if include_state:
            payload["state"] = self._state_payload_unlocked()
        if include_queue:
            payload["queue"] = self._queue_payload_unlocked()
        if track_id:
            payload["track"] = self._repository.get_track(track_id)
        if error:
            payload["error"] = {"message": error}
        return payload

    def _emit_state_changed_unlocked(self) -> None:
        self._events.publish(
            self._build_event_unlocked(event_type="player_state_changed", include_state=True)
        )

    def _emit_position_tick_unlocked(self) -> None:
        self._events.publish(
            self._build_event_unlocked(event_type="player_position_tick", include_state=True)
        )

    def _emit_track_started_unlocked(self, track_id: str) -> None:
        self._events.publish(
            self._build_event_unlocked(
                event_type="player_track_started",
                include_state=True,
                track_id=track_id,
            )
        )

    def _emit_track_finished_unlocked(self, track_id: str | None) -> None:
        self._events.publish(
            self._build_event_unlocked(
                event_type="player_track_finished",
                include_state=True,
                track_id=track_id,
            )
        )

    def _emit_queue_changed_unlocked(self) -> None:
        self._events.publish(
            self._build_event_unlocked(event_type="player_queue_changed", include_queue=True)
        )

    def publish_error(self, message: str) -> None:
        """Publish a player_error event."""
        with self._lock:
            self._events.publish(
                self._build_event_unlocked(event_type="player_error", error=message)
            )

    def _state_payload_unlocked(self) -> dict[str, Any]:
        current_track = self._repository.get_track(self._current_track_id) if self._current_track_id else None
        return {
            "status": self._status,
            "current_track": current_track,
            "position_ms": int(self._position_ms),
            "duration_ms": int(self._duration_ms),
            "volume": float(self._volume),
            "muted": bool(self._muted),
            "shuffle": bool(self._shuffle),
            "repeat_mode": self._repeat_mode,
            "updated_at": self._updated_at,
            "current_queue_index": self._current_queue_index,
        }

    def _queue_payload_unlocked(self) -> dict[str, Any]:
        tracks_map = self._repository.get_tracks(self._queue_track_ids)
        items: list[dict[str, Any]] = []
        for track_id in self._queue_track_ids:
            track = tracks_map.get(track_id)
            if not track:
                continue
            items.append(
                {
                    "track_id": track["track_id"],
                    "artist": track.get("artist", ""),
                    "title": track.get("title", ""),
                    "album": track.get("album", ""),
                    "duration_ms": int(track.get("duration_ms", 0) or 0),
                    "filepath": track.get("filepath", ""),
                }
            )
        return {
            "items": items,
            "current_index": max(0, min(self._current_queue_index, max(0, len(items) - 1))),
            "count": len(items),
        }

    def _deterministic_shuffle(self, track_ids: list[str]) -> list[str]:
        if len(track_ids) <= 1:
            return list(track_ids)
        scored = []
        for track_id in track_ids:
            digest = hashlib.sha1(track_id.encode("utf-8")).hexdigest()
            scored.append((digest, track_id))
        scored.sort(key=lambda item: item[0])
        return [track_id for _, track_id in scored]


_player_service_singleton: PlayerService | None = None
_player_service_lock = RLock()


def get_player_service() -> PlayerService:
    """Return process singleton player service."""
    global _player_service_singleton
    with _player_service_lock:
        if _player_service_singleton is None:
            _player_service_singleton = PlayerService()
        return _player_service_singleton
