import unittest
from unittest import mock

from oracle.acquirers import streamrip


class StreamripProviderTests(unittest.TestCase):
    def test_is_available_uses_executable_lookup(self) -> None:
        with mock.patch("oracle.acquirers.streamrip._find_rip_executable", return_value=None):
            self.assertFalse(streamrip.is_available())

    def test_download_fails_soft_when_not_available(self) -> None:
        with mock.patch("oracle.acquirers.streamrip._find_rip_executable", return_value=None):
            result = streamrip.download("Artist", "Title")
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("source"), "streamrip")

    def test_sanitize_filename_component_removes_windows_invalid_chars(self) -> None:
        cleaned = streamrip._sanitize_filename_component("Do I Wanna Know?: <live>|*")
        self.assertEqual(cleaned, "Do I Wanna Know live")


if __name__ == "__main__":
    unittest.main()
