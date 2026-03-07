import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oracle import ingest_watcher


class IngestWatcherQueueResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "watcher.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                filepath TEXT UNIQUE,
                artist TEXT,
                title TEXT,
                status TEXT DEFAULT 'active'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE acquisition_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT,
                title TEXT,
                status TEXT DEFAULT 'pending',
                added_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                matched_track_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO tracks (track_id, filepath, artist, title, status) VALUES (?, ?, ?, ?, 'active')",
            ("track-123", r"A:\Library\Artist\Album\01 - Title.flac", "Artist", "Title"),
        )
        conn.execute(
            "INSERT INTO acquisition_queue (artist, title, status, error) VALUES (?, ?, 'downloaded', ?)",
            ("Artist", "Title", ingest_watcher._download_path_marker(r"A:\Staging\Artist - Title.flac")),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _connect(self, timeout: float = 10.0):
        return sqlite3.connect(self.db_path, timeout=timeout)

    def test_duplicate_resolution_marks_queue_completed_with_matched_track(self) -> None:
        with mock.patch("oracle.db.schema.get_connection", side_effect=self._connect):
            resolved = ingest_watcher._resolve_duplicate_queue_row(
                r"A:\Library\Artist\Album\01 - Title.flac",
                r"A:\Staging\Artist - Title.flac",
                "Artist",
                "Title",
            )

        self.assertTrue(resolved)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status, matched_track_id, error, completed_at FROM acquisition_queue WHERE id = 1"
        ).fetchone()
        conn.close()

        self.assertEqual(row[0], "completed")
        self.assertEqual(row[1], "track-123")
        self.assertIsNone(row[2])
        self.assertIsNotNone(row[3])

    def test_duplicate_resolution_returns_false_when_library_track_missing(self) -> None:
        with mock.patch("oracle.db.schema.get_connection", side_effect=self._connect):
            resolved = ingest_watcher._resolve_duplicate_queue_row(
                r"A:\Library\Artist\Album\99 - Missing.flac",
                r"A:\Staging\Artist - Title.flac",
                "Artist",
                "Title",
            )

        self.assertFalse(resolved)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status, matched_track_id FROM acquisition_queue WHERE id = 1"
        ).fetchone()
        conn.close()

        self.assertEqual(row[0], "downloaded")
        self.assertIsNone(row[1])

    def test_duplicate_resolution_requeues_when_downloaded_track_mismatches_request(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM acquisition_queue")
        conn.execute(
            "INSERT INTO acquisition_queue (artist, title, status, retry_count, error) VALUES (?, ?, 'downloaded', 0, ?)",
            ("Bear Hands", "Agora", ingest_watcher._download_path_marker(r"A:\Staging\Bear Hands - 2AM.flac")),
        )
        conn.execute("DELETE FROM tracks")
        conn.execute(
            "INSERT INTO tracks (track_id, filepath, artist, title, status) VALUES (?, ?, ?, ?, 'active')",
            ("track-456", r"A:\Music\Bear_Hands\You'll_Pay_For_This\02_2AM.flac", "Bear Hands", "2AM"),
        )
        conn.commit()
        conn.close()

        with mock.patch("oracle.db.schema.get_connection", side_effect=self._connect):
            resolved = ingest_watcher._resolve_duplicate_queue_row(
                r"A:\Music\Bear_Hands\You'll_Pay_For_This\02_2AM.flac",
                r"A:\Staging\Bear Hands - 2AM.flac",
                "Bear Hands",
                "2AM",
            )

        self.assertTrue(resolved)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status, retry_count, error, matched_track_id FROM acquisition_queue ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        self.assertEqual(row[0], "pending")
        self.assertEqual(row[1], 1)
        self.assertIn("duplicate acquisition mismatch", row[2])
        self.assertIsNone(row[3])


if __name__ == "__main__":
    unittest.main()