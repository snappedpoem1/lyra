import unittest

from oracle.enrichers import musicnn


class MusicnnProviderTests(unittest.TestCase):
    def test_provider_fails_soft_when_disabled(self) -> None:
        profile = musicnn.build_track_profile("does-not-exist.flac")
        self.assertEqual(profile, {})


if __name__ == "__main__":
    unittest.main()

