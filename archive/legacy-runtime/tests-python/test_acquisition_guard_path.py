import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from oracle import acquisition
from oracle.acquirers.waterfall import AcquisitionResult


class AcquisitionGuardPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "queue.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE acquisition_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                source TEXT,
                artist TEXT,
                title TEXT,
                status TEXT,
                retry_count INTEGER,
                error TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO acquisition_queue (url, source, artist, title, status, retry_count) VALUES (?, ?, ?, ?, 'pending', 0)",
            ("magnet:?xt=urn:btih:test", "prowlarr", "Artist", "Title"),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _connect(self, timeout: float = 10.0):
        return sqlite3.connect(self.db_path, timeout=timeout)

    def test_guard_reject_blocks_staging_move(self) -> None:
        download_path = Path(self.tmp.name) / "track.mp3"
        download_path.write_bytes(b"fake-audio")

        # Mock waterfall to simulate T4 real-debrid acquisition with guard rejection
        # The new flow: waterfall.acquire → magnet_sources → realdebrid.acquire_from_magnets
        def mock_waterfall_acquire(artist: str, title: str, **kwargs):
            # Simulate guard rejection by returning failed result with error
            return AcquisitionResult(
                success=False,
                tier=4,
                source="realdebrid",
                path=None,
                error="Guard rejected: junk"
            )

        with mock.patch("oracle.acquisition.get_write_mode", return_value="apply_allowed"), \
             mock.patch("oracle.acquisition.get_connection", side_effect=self._connect), \
             mock.patch("oracle.acquirers.waterfall.acquire", side_effect=mock_waterfall_acquire):
            stats = acquisition.process_queue(limit=1)

        self.assertEqual(stats["completed"], 0)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status, retry_count, error FROM acquisition_queue WHERE id = 1"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "pending")
        self.assertEqual(row[1], 1)
        self.assertIn("Guard rejected", row[2] or "")


if __name__ == "__main__":
    unittest.main()
