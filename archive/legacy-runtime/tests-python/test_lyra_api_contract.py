from __future__ import annotations

import lyra_api
import oracle.api.blueprints.core as core_bp
import oracle.api.blueprints.library as library_bp
import oracle.api.blueprints.radio as radio_bp
import oracle.api.blueprints.vibes as vibes_bp
import oracle.api.helpers as api_helpers
import oracle.doctor
from oracle.doctor import CheckResult


def test_health_contract(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert "status" in payload
    assert "ok" in payload
    assert "service" in payload
    assert "version" in payload
    assert "timestamp" in payload
    assert "profile" in payload
    assert "write_mode" in payload
    assert "db" in payload
    assert "database" in payload
    assert "library" in payload
    assert "feature_flags" in payload
    assert "features" in payload
    assert "auth" in payload
    assert "cors" in payload


def test_doctor_contract(client, monkeypatch):
    monkeypatch.setattr(
        oracle.doctor,
        "run_doctor",
        lambda: [
            CheckResult(name="Python", status="PASS", details="3.12.0"),
            CheckResult(name="ChromaDB", status="FAIL", details="Missing"),
        ],
    )

    response = client.get("/api/doctor")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload == [
        {"name": "Python", "status": "PASS", "details": "3.12.0"},
        {"name": "ChromaDB", "status": "FAIL", "details": "Missing"},
    ]


def test_playlist_detail_contract(client, monkeypatch):
    _vibe_detail = {
        "id": "test-playlist",
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
    }
    # Patch both the vibes blueprint (for old vibes tests) and api_helpers
    # (where the playlists blueprint imports _load_vibe_detail lazily)
    monkeypatch.setattr(vibes_bp, "_load_vibe_detail", lambda playlist_id: _vibe_detail)
    monkeypatch.setattr(api_helpers, "_load_vibe_detail", lambda playlist_id: _vibe_detail)
    response = client.get("/api/playlists/test-playlist")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["id"] == "test-playlist"
    assert isinstance(payload["tracks"], list)


def test_radio_engine_is_available():
    assert radio_bp._radio_engine is not None


def test_dossier_contract(client, monkeypatch):
    monkeypatch.setattr(library_bp, "_load_track", lambda track_id: {
        "track_id": track_id,
        "artist": "Artist",
        "title": "Title",
        "filepath": "C:/music/file.flac",
    })
    monkeypatch.setattr(library_bp, "_architect_engine", None)
    monkeypatch.setattr(library_bp, "_lore_engine", None)
    monkeypatch.setattr(library_bp, "_dna_engine", None)
    monkeypatch.setattr(library_bp, "_agent_engine", None)

    response = client.get("/api/tracks/track-1/dossier")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["track"]["track_id"] == "track-1"
    assert "provenance_notes" in payload
    assert "acquisition_notes" in payload


def test_auth_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("LYRA_API_TOKEN", "secret")
    response = client.get("/api/vibes")
    assert response.status_code == 401
    response = client.get("/api/vibes", headers={"Authorization": "Bearer secret"})
    assert response.status_code in {200, 500}
    monkeypatch.delenv("LYRA_API_TOKEN", raising=False)


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

    fake_factory = lambda timeout=10.0: FakeConn()
    monkeypatch.setattr(library_bp, "get_connection", fake_factory)
    monkeypatch.setattr(api_helpers, "get_connection", fake_factory)

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

    monkeypatch.setattr(library_bp, "get_connection", lambda timeout=10.0: FakeConn())

    artists = client.get("/api/library/artists?q=Artist")
    assert artists.status_code == 200
    assert artists.get_json()["artists"][0]["name"] == "Artist A"

    albums = client.get("/api/library/albums?artist=Artist%20A")
    assert albums.status_code == 200
    assert albums.get_json()["albums"][1]["name"] == "Singles / Unknown Album"


def test_library_artist_detail_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        library_bp,
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
        library_bp,
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
