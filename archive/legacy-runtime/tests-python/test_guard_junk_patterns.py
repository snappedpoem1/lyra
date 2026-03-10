import unittest

from oracle.acquirers.guard import _check_junk


class GuardJunkPatternTests(unittest.TestCase):
    def test_under_cover_of_darkness_not_rejected_as_cover_version(self) -> None:
        result = _check_junk("The Strokes", "Under Cover of Darkness")
        self.assertIsNone(result)

    def test_explicit_cover_title_is_rejected(self) -> None:
        result = _check_junk("Artist", "Song (Cover)")
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "junk")


if __name__ == "__main__":
    unittest.main()
