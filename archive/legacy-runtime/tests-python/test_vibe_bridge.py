"""Contract tests for the vibe → saved_playlists bridge — Wave 15.

Monkeypatches ``generate_vibe`` and ``get_connection`` in oracle.vibes so
that ``save_vibe`` runs entirely against an isolated in-memory SQLite
database without touching CLAP embeddings or the live library.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import oracle.vibes as vibes_module
from oracle.types import PlaylistRun, PlaylistTrack, TrackReason

# ---------------------------------------------------------------------------
# DDL  (minimal for save_vibe)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vibe_profiles (
    name TEXT PRIMARY KEY,
    query_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    track_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vibe_tracks (
    vibe_name TEXT NOT NULL,
    track_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (vibe_name, track_id)
);
CREATE TABLE IF NOT EXISTS saved_playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);
CREATE TABLE IF NOT EXISTS saved_playlist_tracks (
    playlist_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at REAL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (playlist_id, track_id)
);
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY,
    filepath TEXT,
    artist TEXT,
    title TEXT
);
-- Seed two tracks so save_vibe can resolve them
INSERT INTO tracks VALUES ('tr1', '/music/a.flac', 'Band A', 'Song X');
INSERT INTO tracks VALUES ('tr2', '/music/b.flac', 'Band B', 'Song Y');
"""


def _make_run(paths: list[str]) -> PlaylistRun:
    """Build a minimal PlaylistRun for the given file paths."""
    tracks = [
        PlaylistTrack(
            path=p,
            artist=f"Artist {i}",
            title=f"Title {i}",
            rank=i + 1,
            global_score=0.9 - i * 0.1,
            reasons=[TrackReason(type="semantic", score=0.9, text="test")],
        )
        for i, p in enumerate(paths)
    ]
    return PlaylistRun(
        uuid=str(uuid.uuid4()),
        prompt="test query",
        created_at=datetime.now(tz=timezone.utc),
        tracks=tracks,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "vibe_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def patch_vibes(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire save_vibe to the test DB and mock generate_vibe."""
    monkeypatch.setattr(
        vibes_module,
        "get_connection",
        lambda timeout=10.0: sqlite3.connect(str(db), timeout=timeout),
    )
    monkeypatch.setattr(
        vibes_module,
        "get_write_mode",
        lambda: "apply_allowed",
    )
    # generate_vibe must return a run whose track paths exist in `tracks`
    monkeypatch.setattr(
        vibes_module,
        "generate_vibe",
        lambda prompt, n=20, vibe_name=None: _make_run(
            ["/music/a.flac", "/music/b.flac"]
        ),
    )


def _get_conn(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVibeSavedPlaylistsBridge:
    def test_save_vibe_creates_saved_playlist_row(self, db: Path) -> None:
        vibes_module.save_vibe("chill drive", "chill music", n=10)
        conn = _get_conn(db)
        row = conn.execute(
            "SELECT * FROM saved_playlists WHERE name = ?", ("chill drive",)
        ).fetchone()
        conn.close()
        assert row is not None, "saved_playlists row was not created"

    def test_save_vibe_populates_saved_playlist_tracks(self, db: Path) -> None:
        vibes_module.save_vibe("chill drive", "chill music", n=10)
        conn = _get_conn(db)
        playlist_id = conn.execute(
            "SELECT id FROM saved_playlists WHERE name = ?", ("chill drive",)
        ).fetchone()["id"]
        rows = conn.execute(
            "SELECT track_id FROM saved_playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchall()
        conn.close()
        assert len(rows) == 2

    def test_playlist_id_is_deterministic(self, db: Path) -> None:
        """Re-saving the same name must produce the exact same playlist UUID."""
        vibes_module.save_vibe("steady vibes", "steady", n=10)
        conn = _get_conn(db)
        pid1 = conn.execute(
            "SELECT id FROM saved_playlists WHERE name = ?", ("steady vibes",)
        ).fetchone()["id"]
        conn.close()

        # Save again — should upsert, not create a second row
        vibes_module.save_vibe("steady vibes", "steady updated", n=10)
        conn = _get_conn(db)
        count = conn.execute(
            "SELECT COUNT(*) FROM saved_playlists WHERE name = ?", ("steady vibes",)
        ).fetchone()[0]
        pid2 = conn.execute(
            "SELECT id FROM saved_playlists WHERE name = ?", ("steady vibes",)
        ).fetchone()["id"]
        conn.close()

        assert count == 1, "re-save must not create a duplicate saved_playlists row"
        assert pid1 == pid2, "playlist UUID must be deterministic across saves"

    def test_resave_replaces_tracks(self, db: Path) -> None:
        """The second save must not accumulate more tracks than the first."""
        vibes_module.save_vibe("evolving", "query1", n=10)
        vibes_module.save_vibe("evolving", "query2", n=10)

        conn = _get_conn(db)
        playlist_id = conn.execute(
            "SELECT id FROM saved_playlists WHERE name = ?", ("evolving",)
        ).fetchone()["id"]
        count = conn.execute(
            "SELECT COUNT(*) FROM saved_playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()[0]
        conn.close()

        # generate_vibe always returns 2 tracks in the test fixture
        assert count == 2

    def test_description_is_query_string(self, db: Path) -> None:
        vibes_module.save_vibe("dark ambient", "dark ambient late night", n=5)
        conn = _get_conn(db)
        desc = conn.execute(
            "SELECT description FROM saved_playlists WHERE name = ?", ("dark ambient",)
        ).fetchone()["description"]
        conn.close()
        assert desc == "dark ambient late night"

    def test_playlist_id_matches_expected_uuid5(self, db: Path) -> None:
        vibes_module.save_vibe("golden hour", "sunset warmth", n=5)
        expected_id = str(uuid.uuid5(vibes_module._VIBE_NS, "lyra:vibe:golden hour"))
        conn = _get_conn(db)
        row = conn.execute(
            "SELECT id FROM saved_playlists WHERE name = ?", ("golden hour",)
        ).fetchone()
        conn.close()
        assert row["id"] == expected_id
