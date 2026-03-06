"""Persistence and lookup helpers for canonical player state."""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)


TrackRow = dict[str, Any]


class PlayerRepository:
    """Read/write access layer for player state and queue tables."""

    def ensure_tables(self) -> None:
        """Create canonical player tables when missing."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS player_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    status TEXT NOT NULL DEFAULT 'idle',
                    current_track_id TEXT,
                    current_queue_index INTEGER NOT NULL DEFAULT 0,
                    position_ms INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    volume REAL NOT NULL DEFAULT 0.82,
                    muted INTEGER NOT NULL DEFAULT 0,
                    shuffle INTEGER NOT NULL DEFAULT 0,
                    repeat_mode TEXT NOT NULL DEFAULT 'off',
                    updated_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS player_queue (
                    position INTEGER PRIMARY KEY,
                    track_id TEXT NOT NULL,
                    added_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_player_queue_track_id ON player_queue(track_id)"
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO player_state
                (id, status, current_track_id, current_queue_index, position_ms, duration_ms, volume, muted, shuffle, repeat_mode, updated_at)
                VALUES (1, 'idle', NULL, 0, 0, 0, 0.82, 0, 0, 'off', ?)
                """,
                (time.time(),),
            )
            conn.commit()
        finally:
            conn.close()

    def load_state(self) -> dict[str, Any]:
        """Load persisted singleton player state."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, current_track_id, current_queue_index, position_ms, duration_ms,
                       volume, muted, shuffle, repeat_mode, updated_at
                FROM player_state
                WHERE id = 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return {
                    "status": "idle",
                    "current_track_id": None,
                    "current_queue_index": 0,
                    "position_ms": 0,
                    "duration_ms": 0,
                    "volume": 0.82,
                    "muted": 0,
                    "shuffle": 0,
                    "repeat_mode": "off",
                    "updated_at": time.time(),
                }
            return {
                "status": row[0] or "idle",
                "current_track_id": row[1],
                "current_queue_index": int(row[2] or 0),
                "position_ms": int(row[3] or 0),
                "duration_ms": int(row[4] or 0),
                "volume": float(row[5] or 0.82),
                "muted": int(row[6] or 0),
                "shuffle": int(row[7] or 0),
                "repeat_mode": row[8] or "off",
                "updated_at": float(row[9] or time.time()),
            }
        finally:
            conn.close()

    def load_queue(self) -> list[str]:
        """Load queue track ids in position order."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT track_id FROM player_queue ORDER BY position ASC")
            return [str(row[0]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_state(
        self,
        *,
        status: str,
        current_track_id: str | None,
        current_queue_index: int,
        position_ms: int,
        duration_ms: int,
        volume: float,
        muted: bool,
        shuffle: bool,
        repeat_mode: str,
        updated_at: float,
    ) -> None:
        """Persist singleton state."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO player_state
                (id, status, current_track_id, current_queue_index, position_ms, duration_ms, volume, muted, shuffle, repeat_mode, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    current_track_id = excluded.current_track_id,
                    current_queue_index = excluded.current_queue_index,
                    position_ms = excluded.position_ms,
                    duration_ms = excluded.duration_ms,
                    volume = excluded.volume,
                    muted = excluded.muted,
                    shuffle = excluded.shuffle,
                    repeat_mode = excluded.repeat_mode,
                    updated_at = excluded.updated_at
                """,
                (
                    status,
                    current_track_id,
                    current_queue_index,
                    position_ms,
                    duration_ms,
                    volume,
                    1 if muted else 0,
                    1 if shuffle else 0,
                    repeat_mode,
                    updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_queue(self, track_ids: list[str]) -> None:
        """Replace queue in one transaction."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM player_queue")
            cursor.executemany(
                "INSERT INTO player_queue (position, track_id, added_at) VALUES (?, ?, ?)",
                [(index, track_id, time.time()) for index, track_id in enumerate(track_ids)],
            )
            conn.commit()
        finally:
            conn.close()

    def get_track(self, track_id: str) -> TrackRow | None:
        """Return one track metadata row."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT track_id, artist, title, album, duration, filepath
                FROM tracks
                WHERE track_id = ?
                LIMIT 1
                """,
                (track_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            duration_value = row[4]
            duration_ms = 0
            if duration_value is not None:
                duration_ms = max(0, int(float(duration_value) * 1000))
            return {
                "track_id": str(row[0]),
                "artist": str(row[1] or ""),
                "title": str(row[2] or ""),
                "album": str(row[3] or ""),
                "duration_ms": duration_ms,
                "filepath": str(row[5] or ""),
            }
        finally:
            conn.close()

    def get_tracks(self, track_ids: list[str]) -> dict[str, TrackRow]:
        """Fetch metadata for multiple track ids."""
        if not track_ids:
            return {}
        placeholders = ",".join("?" for _ in track_ids)
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT track_id, artist, title, album, duration, filepath
                FROM tracks
                WHERE track_id IN ({placeholders})
                """,
                tuple(track_ids),
            )
            rows = cursor.fetchall()
            out: dict[str, TrackRow] = {}
            for row in rows:
                duration_value = row[4]
                duration_ms = 0
                if duration_value is not None:
                    duration_ms = max(0, int(float(duration_value) * 1000))
                out[str(row[0])] = {
                    "track_id": str(row[0]),
                    "artist": str(row[1] or ""),
                    "title": str(row[2] or ""),
                    "album": str(row[3] or ""),
                    "duration_ms": duration_ms,
                    "filepath": str(row[5] or ""),
                }
            return out
        finally:
            conn.close()

    def record_playback(
        self,
        *,
        track_id: str,
        context: str,
        skipped: bool,
        completion_rate: float,
        rating: int | None = None,
    ) -> None:
        """Persist one playback row for taste learning and history."""
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO playback_history (track_id, context, session_id, skipped, completion_rate, rating)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    context,
                    "backend_player",
                    1 if skipped else 0,
                    completion_rate,
                    rating,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            logger.warning("playback_history write failed for %s: %s", track_id, exc)
        finally:
            conn.close()
