import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from oracle import acquisition


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
<<<<<<< HEAD
=======
                artist TEXT,
                title TEXT,
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                status TEXT,
                retry_count INTEGER,
                error TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
<<<<<<< HEAD
            "INSERT INTO acquisition_queue (url, source, status, retry_count) VALUES (?, ?, 'pending', 0)",
            ("magnet:?xt=urn:btih:test", "prowlarr"),
=======
            "INSERT INTO acquisition_queue (url, source, artist, title, status, retry_count) VALUES (?, ?, ?, ?, 'pending', 0)",
            ("magnet:?xt=urn:btih:test", "prowlarr", "Artist", "Title"),
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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

        with mock.patch("oracle.acquisition.get_write_mode", return_value="apply_allowed"), \
             mock.patch("oracle.acquisition.get_connection", side_effect=self._connect), \
<<<<<<< HEAD
=======
             mock.patch(
                 "oracle.acquisition.guard_acquisition",
                 return_value=SimpleNamespace(
                     allowed=True,
                     confidence=1.0,
                     rejection_reason=None,
                 ),
             ), \
>>>>>>> fc77b41 (Update workspace state and diagnostics)
             mock.patch("oracle.acquisition.prowlarr_rd.add_to_real_debrid", return_value="tid"), \
             mock.patch("oracle.acquisition.prowlarr_rd.select_files"), \
             mock.patch(
                 "oracle.acquisition.prowlarr_rd.poll_real_debrid",
                 return_value={"status": "downloaded"},
             ), \
             mock.patch(
                 "oracle.acquisition.prowlarr_rd.download_from_real_debrid",
                 return_value=[download_path],
             ), \
             mock.patch("oracle.acquisition.prowlarr_rd.move_to_staging") as move_to_staging, \
             mock.patch(
                 "oracle.acquisition.guard_file",
                 return_value=SimpleNamespace(
                     allowed=False,
                     confidence=0.0,
                     rejection_reason="junk",
                     artist="",
                     title="",
                 ),
             ):
            stats = acquisition.process_queue(limit=1)

        self.assertEqual(stats["completed"], 0)
        move_to_staging.assert_not_called()

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
