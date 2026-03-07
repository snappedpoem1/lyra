from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

import lyra_api
import oracle.api.blueprints.playlists as playlists_bp


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Test client wired to an in-memory playlist database."""
    db_path = tmp_path / "playlists_test.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE saved_playlists (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            );
            CREATE TABLE saved_playlist_tracks (
                playlist_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                added_at REAL DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (playlist_id, track_id),
                FOREIGN KEY (playlist_id) REFERENCES saved_playlists(id) ON DELETE CASCADE
            );
            CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                album TEXT,
                duration_ms INTEGER,
                filepath TEXT,
                track_number INTEGER,
                status TEXT DEFAULT 'active'
            );
            INSERT INTO tracks VALUES ('tr1','Artist A','Song 1','Alb A',180000,'/m/1.flac',1,'active');
            INSERT INTO tracks VALUES ('tr2','Artist A','Song 2','Alb A',190000,'/m/2.flac',2,'active');
            INSERT INTO tracks VALUES ('tr3','Artist B','Other',  'Alb B',200000,'/m/3.flac',1,'active');
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        playlists_bp, "get_connection",
        lambda timeout=10.0: sqlite3.connect(db_path, timeout=timeout),
    )
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as tc:
        yield tc


# ── list ──────────────────────────────────────────────────────────────────


def test_list_playlists_empty(client: Any) -> None:
    r = client.get("/api/playlists")
    assert r.status_code == 200
    assert r.get_json()["playlists"] == []


# ── create ────────────────────────────────────────────────────────────────


def test_create_playlist(client: Any) -> None:
    r = client.post("/api/playlists", json={"name": "Night Drive"})
    assert r.status_code == 201
    pl = r.get_json()["playlist"]
    assert pl["name"] == "Night Drive"
    assert pl["id"]


def test_create_playlist_missing_name(client: Any) -> None:
    r = client.post("/api/playlists", json={})
    assert r.status_code == 400


def test_create_playlist_with_tracks(client: Any) -> None:
    r = client.post(
        "/api/playlists",
        json={"name": "Pre-seeded", "track_ids": ["tr1", "tr2"]},
    )
    assert r.status_code == 201
    pl = r.get_json()["playlist"]
    assert pl["track_count"] == 2


def test_list_shows_created_playlist(client: Any) -> None:
    client.post("/api/playlists", json={"name": "Visible"})
    r = client.get("/api/playlists")
    names = [p["name"] for p in r.get_json()["playlists"]]
    assert "Visible" in names


# ── detail ────────────────────────────────────────────────────────────────


def test_get_playlist_detail(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "Detail Test"})
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.get(f"/api/playlists/{pl_id}")
    assert r.status_code == 200
    data = r.get_json()
    assert data["title"] == "Detail Test"
    assert "tracks" in data


def test_get_playlist_detail_not_found(client: Any) -> None:
    r = client.get("/api/playlists/no-such-id-xyz")
    assert r.status_code == 404


# ── delete ────────────────────────────────────────────────────────────────


def test_delete_playlist(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "Deletable"})
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.delete(f"/api/playlists/{pl_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "deleted"
    assert client.get(f"/api/playlists/{pl_id}").status_code == 404


def test_delete_playlist_not_found(client: Any) -> None:
    r = client.delete("/api/playlists/ghost")
    assert r.status_code == 404


# ── add / remove tracks ───────────────────────────────────────────────────


def test_add_tracks_to_playlist(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "Track Test"})
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.post(f"/api/playlists/{pl_id}/tracks", json={"track_ids": ["tr1", "tr2"]})
    assert r.status_code == 200
    assert r.get_json()["inserted"] == 2


def test_add_tracks_deduplicates(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "Dedup"})
    pl_id = cr.get_json()["playlist"]["id"]
    client.post(f"/api/playlists/{pl_id}/tracks", json={"track_ids": ["tr1"]})
    r = client.post(f"/api/playlists/{pl_id}/tracks", json={"track_ids": ["tr1", "tr3"]})
    assert r.get_json()["inserted"] == 1  # tr1 already present


def test_add_tracks_missing_payload(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "Empty Add"})
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.post(f"/api/playlists/{pl_id}/tracks", json={})
    assert r.status_code == 400


def test_add_tracks_playlist_not_found(client: Any) -> None:
    r = client.post("/api/playlists/ghost/tracks", json={"track_ids": ["tr1"]})
    assert r.status_code == 404


def test_remove_track_from_playlist(client: Any) -> None:
    cr = client.post(
        "/api/playlists",
        json={"name": "Remove Test", "track_ids": ["tr1", "tr2"]},
    )
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.delete(f"/api/playlists/{pl_id}/tracks/tr1")
    assert r.status_code == 200
    assert r.get_json()["status"] == "removed"
    # Confirm detail now has only 1 track
    detail = client.get(f"/api/playlists/{pl_id}").get_json()
    assert detail["trackCount"] == 1


def test_remove_track_not_in_playlist(client: Any) -> None:
    cr = client.post("/api/playlists", json={"name": "No Remove"})
    pl_id = cr.get_json()["playlist"]["id"]
    r = client.delete(f"/api/playlists/{pl_id}/tracks/nonexistent")
    assert r.status_code == 404
