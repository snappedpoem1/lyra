import unittest
from unittest import mock

from oracle import console


class ConsoleWrapperTests(unittest.TestCase):
    def test_cmd_hunt_uses_pipeline_wrappers(self) -> None:
        fake_result = {
            "state": "completed",
            "result": {"filepath": r"A:\\music\\Active Music\\Artist - Title.flac"},
        }
        with mock.patch("oracle.pipeline.start_acquisition", return_value="job-1") as start_mock, \
             mock.patch("oracle.pipeline.run_pipeline", return_value=fake_result) as run_mock:
            code = console.cmd_hunt("Artist - Title")

        self.assertEqual(code, 0)
        start_mock.assert_called_once_with("Artist - Title")
        run_mock.assert_called_once_with("job-1")


if __name__ == "__main__":
    unittest.main()
