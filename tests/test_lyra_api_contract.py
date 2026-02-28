from __future__ import annotations

import lyra_api


def test_health_contract(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert "timestamp" in payload
    assert "profile" in payload
    assert "db" in payload
    assert "library" in payload
    assert "feature_flags" in payload


def test_playlist_detail_contract(client, monkeypatch):
    monkeypatch.setattr(
        lyra_api,
        "_load_vibe_detail",
        lambda playlist_id: {
            "id": playlist_id,
            "kind": "vibe",
            "title": "Test Playlist",
            "subtitle": "prompt",
            "narrative": "story",
            "trackCount": 1,
            "freshnessLabel": "Saved vibe",
            "coverMosaic": ["T"],
            "emotionalSignature": [],
            "tracks": [{"track_id": "track-1", "artist": "A", "title": "B"}],
            "storyBeats": ["beat"],
            "arc": [{"step": 1, "energy": 0.4, "valence": 0.5, "tension": 0.3}],
            "relatedPlaylists": [],
            "oraclePivots": [],
        },
    )
    response = client.get("/api/playlists/test-playlist")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["id"] == "test-playlist"
    assert isinstance(payload["tracks"], list)


def test_dossier_contract(client, monkeypatch):
    monkeypatch.setattr(lyra_api, "_load_track", lambda track_id: {
        "track_id": track_id,
        "artist": "Artist",
        "title": "Title",
        "filepath": "C:/music/file.flac",
    })
    monkeypatch.setattr(lyra_api, "architect_engine", None)
    monkeypatch.setattr(lyra_api, "lore_engine", None)
    monkeypatch.setattr(lyra_api, "dna_engine", None)
    monkeypatch.setattr(lyra_api, "agent_engine", None)

    response = client.get("/api/tracks/track-1/dossier")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["track"]["track_id"] == "track-1"
    assert "provenance_notes" in payload
    assert "acquisition_notes" in payload


def test_auth_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(lyra_api, "API_TOKEN", "secret")
    response = client.get("/api/vibes")
    assert response.status_code == 401
    response = client.get("/api/vibes", headers={"Authorization": "Bearer secret"})
    assert response.status_code in {200, 500}
    monkeypatch.setattr(lyra_api, "API_TOKEN", "")


import pytest


@pytest.fixture
def client():
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as client:
        yield client
