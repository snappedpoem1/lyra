import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oracle.acquirers.smart_pipeline import AcquisitionRequest, AcquisitionResult, SmartAcquisition


class SmartPipelineQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE acquisition_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT,
                title TEXT,
                album TEXT,
                spotify_uri TEXT,
                priority_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'pending',
                added_at TEXT DEFAULT (datetime('now')),
                retry_count INTEGER DEFAULT 0,
                completed_at TEXT,
                error TEXT
            )
            """
        )
        c.execute("INSERT INTO acquisition_queue (artist, title, status, priority_score, retry_count) VALUES ('A', 'T', 'pending', 10, 0)")
        c.execute("INSERT INTO acquisition_queue (artist, title, status, priority_score, retry_count) VALUES ('Legacy', 'Done', 'complete', 1, 0)")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _connect(self, timeout: float = 10.0):
        return sqlite3.connect(self.db_path)

    def test_process_queue_uses_current_schema_and_normalizes_status(self) -> None:
        with mock.patch("oracle.acquirers.smart_pipeline.get_connection", side_effect=self._connect):
            pipeline = SmartAcquisition(library_path=Path(self.tmp.name), require_validation=False)
            try:
                fake_result = AcquisitionResult(
                    success=True,
                    request=AcquisitionRequest(artist="A", title="T"),
                )
                with mock.patch.object(pipeline, "acquire_batch", return_value=[fake_result]):
                    results = pipeline.process_queue(limit=1)

                self.assertEqual(len(results), 1)
                self.assertEqual(pipeline.last_queue_summary["succeeded"], 1)

                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute("SELECT status FROM acquisition_queue WHERE artist='A' AND title='T'")
                self.assertEqual(c.fetchone()[0], "completed")
                c.execute("SELECT status FROM acquisition_queue WHERE artist='Legacy' AND title='Done'")
                self.assertEqual(c.fetchone()[0], "completed")
                conn.close()
            finally:
                pipeline.close()

    def test_process_queue_retries_then_fails(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM acquisition_queue")
        conn.execute(
            "INSERT INTO acquisition_queue (artist, title, status, priority_score, retry_count) VALUES ('B', 'Fail', 'pending', 5, 2)"
        )
        conn.commit()
        conn.close()

        with mock.patch("oracle.acquirers.smart_pipeline.get_connection", side_effect=self._connect):
            pipeline = SmartAcquisition(library_path=Path(self.tmp.name), require_validation=False)
            try:
                fake_result = AcquisitionResult(
                    success=False,
                    request=AcquisitionRequest(artist="B", title="Fail"),
                    rejection_reason="No source",
                )
                with mock.patch.object(pipeline, "acquire_batch", return_value=[fake_result]):
                    pipeline.process_queue(limit=1)

                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute("SELECT status, retry_count FROM acquisition_queue WHERE artist='B' AND title='Fail'")
                status, retries = c.fetchone()
                conn.close()

                self.assertEqual(status, "failed")
                self.assertEqual(retries, 3)
                self.assertEqual(pipeline.last_queue_summary["rejected"], 1)
            finally:
                pipeline.close()


if __name__ == "__main__":
    unittest.main()
