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


def test_library_tracks_filters(client, monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.calls = 0

        def execute(self, query, params=()):
            self.calls += 1
            self.last_query = query
            self.last_params = params
            return self

        def fetchone(self):
            return (2,)

        def fetchall(self):
            if "SELECT artist, COUNT(*)" in self.last_query:
                return [("Artist A", 2)]
            if "SELECT COALESCE(album, ''), COUNT(*)" in self.last_query:
                return [("Album A", 2)]
            return [
                ("track-1", "Artist A", "Song 1", "Album A", "2020", "", 0.9, 180, "C:/music/song1.flac"),
                ("track-2", "Artist A", "Song 2", "Album A", "2021", "", 0.8, 210, "C:/music/song2.flac"),
            ]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(lyra_api, "get_connection", lambda timeout=10.0: FakeConn())

    response = client.get("/api/library/tracks?artist=Artist%20A&album=Album%20A&q=Song")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artist"] == "Artist A"
    assert payload["album"] == "Album A"
    assert payload["artists"][0]["name"] == "Artist A"
    assert payload["albums"][0]["name"] == "Album A"
    assert len(payload["tracks"]) == 2


def test_library_navigation_endpoints(client, monkeypatch):
    class FakeCursor:
        def execute(self, query, params=()):
            self.last_query = query
            return self

        def fetchall(self):
            if "SELECT artist, COUNT(*)" in self.last_query:
                return [("Artist A", 4), ("Artist B", 2)]
            return [("Album A", 3), ("", 1)]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(lyra_api, "get_connection", lambda timeout=10.0: FakeConn())

    artists = client.get("/api/library/artists?q=Artist")
    assert artists.status_code == 200
    assert artists.get_json()["artists"][0]["name"] == "Artist A"

    albums = client.get("/api/library/albums?artist=Artist%20A")
    assert albums.status_code == 200
    assert albums.get_json()["albums"][1]["name"] == "Singles / Unknown Album"


def test_library_artist_detail_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        lyra_api,
        "_fetch_library_tracks",
        lambda query="", artist="", album="", limit=200, offset=0: [
            {"track_id": "track-1", "artist": artist or "Artist A", "title": "Song 1", "album": "Album A", "year": "2020"},
            {"track_id": "track-2", "artist": artist or "Artist A", "title": "Song 2", "album": "", "year": "2021"},
        ],
    )
    response = client.get("/api/library/artists/Artist%20A")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artist"] == "Artist A"
    assert payload["album_count"] == 2
    assert payload["albums"][1]["name"] == "Singles / Unknown Album"


def test_library_album_detail_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        lyra_api,
        "_fetch_library_tracks",
        lambda query="", artist="", album="", limit=200, offset=0: [
            {"track_id": "track-1", "artist": artist or "Artist A", "title": "Song 1", "album": album or "Album A", "year": "2020"},
        ],
    )
    response = client.get("/api/library/albums/Album%20A?artist=Artist%20A")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artist"] == "Artist A"
    assert payload["album"] == "Album A"
    assert payload["track_count"] == 1


import pytest


@pytest.fixture
def client():
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as client:
        yield client
