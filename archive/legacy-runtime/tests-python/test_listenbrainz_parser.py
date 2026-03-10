from __future__ import annotations

from oracle.integrations.listenbrainz import _parse_top_recordings_payload


def test_parse_top_recordings_payload_accepts_list_shape() -> None:
    payload = [
        {
            "artist_name": "Coldplay",
            "recording_name": "Viva la Vida",
            "total_listen_count": 1234,
            "recording_mbid": "abc",
        }
    ]
    parsed = _parse_top_recordings_payload(payload, "Fallback Artist")
    assert parsed == [
        {
            "artist": "Coldplay",
            "title": "Viva la Vida",
            "listen_count": 1234,
            "recording_mbid": "abc",
        }
    ]


def test_parse_top_recordings_payload_accepts_dict_shape() -> None:
    payload = {
        "recordings": [
            {
                "recording_name": "Yellow",
                "listen_count": "77",
            }
        ]
    }
    parsed = _parse_top_recordings_payload(payload, "Coldplay")
    assert parsed[0]["artist"] == "Coldplay"
    assert parsed[0]["title"] == "Yellow"
    assert parsed[0]["listen_count"] == 77
