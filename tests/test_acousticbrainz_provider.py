import unittest
from unittest import mock

from oracle.enrichers import acousticbrainz


class AcousticBrainzProviderTests(unittest.TestCase):
    def test_build_track_profile_uses_recording_mbid(self) -> None:
        fake_payload = {
            "highlevel": {
                "genre_rosamerica": {"value": "rock"},
                "mood_happy": {"all": {"happy": 0.84}},
                "mood_relaxed": {"all": {"relaxed": 0.21}},
            }
        }

        with mock.patch("oracle.enrichers.acousticbrainz._request", return_value=fake_payload):
            profile = acousticbrainz.build_track_profile(
                artist="Test Artist",
                title="Test Title",
                recording_mbid="1234-5678",
            )

        self.assertEqual(profile.get("provider"), "acousticbrainz")
        self.assertEqual(profile.get("recording_mbid"), "1234-5678")
        self.assertIn("rock", profile.get("tags", []))
        self.assertIn("mood_happy", profile.get("mood_scores", {}))

    def test_build_track_profile_returns_empty_without_mbid(self) -> None:
        with mock.patch("oracle.enrichers.acousticbrainz._request", return_value={}):
            profile = acousticbrainz.build_track_profile(artist="", title="")
        self.assertEqual(profile, {})


if __name__ == "__main__":
    unittest.main()

