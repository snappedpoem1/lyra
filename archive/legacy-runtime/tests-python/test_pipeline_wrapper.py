import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oracle.pipeline import Pipeline


class PipelineWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "pipeline.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _connect(self, timeout: float = 10.0):
        return sqlite3.connect(self.db_path)

    def test_run_delegates_to_smart_pipeline(self) -> None:
        fake_acquire_result = mock.Mock(
            success=True,
            filepath=Path(self.tmp.name) / "ok.flac",
            quality="flac",
            tier_used=1,
            rejection_reason=None,
            elapsed=0.1,
        )

        with mock.patch("oracle.pipeline.get_connection", side_effect=self._connect), \
             mock.patch("oracle.pipeline.LIBRARY_BASE", Path(self.tmp.name)), \
             mock.patch("oracle.pipeline.SmartAcquisition") as smart_cls:
            smart = smart_cls.return_value
            smart.acquire.return_value = fake_acquire_result

            pipeline = Pipeline()
            result = pipeline.run("Artist - Title")

        self.assertEqual(result["state"], "completed")
        smart_cls.assert_called_once()
        smart.acquire.assert_called_once()

    def test_run_existing_completed_job_returns_cached_result(self) -> None:
        with mock.patch("oracle.pipeline.get_connection", side_effect=self._connect), \
             mock.patch("oracle.pipeline.LIBRARY_BASE", Path(self.tmp.name)), \
             mock.patch("oracle.pipeline.SmartAcquisition") as smart_cls:
            pipeline = Pipeline()
            job_id = pipeline.create_job("Artist - Title")
            pipeline.update_job(job_id, "completed", result={"job_id": job_id, "success": True})

            result = pipeline.run(job_id)

        self.assertEqual(result["state"], "completed")
        smart_cls.assert_not_called()

    def test_run_existing_failed_job_retries(self) -> None:
        fake_acquire_result = mock.Mock(
            success=True,
            filepath=Path(self.tmp.name) / "retried.flac",
            quality="flac",
            tier_used=2,
            rejection_reason=None,
            elapsed=0.2,
        )

        with mock.patch("oracle.pipeline.get_connection", side_effect=self._connect), \
             mock.patch("oracle.pipeline.LIBRARY_BASE", Path(self.tmp.name)), \
             mock.patch("oracle.pipeline.SmartAcquisition") as smart_cls:
            smart = smart_cls.return_value
            smart.acquire.return_value = fake_acquire_result

            pipeline = Pipeline()
            job_id = pipeline.create_job("Artist - Title")
            pipeline.update_job(job_id, "failed", error="old error")
            result = pipeline.run(job_id)

        self.assertEqual(result["state"], "completed")
        smart_cls.assert_called_once()
        smart.acquire.assert_called_once()


if __name__ == "__main__":
    unittest.main()
