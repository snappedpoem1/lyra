"""Lyra Oracle database schema and utilities."""

from __future__ import annotations

from pathlib import Path
import hashlib
import os
import sqlite3
import time
from typing import Optional

from oracle.config import LYRA_DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = LYRA_DB_PATH

VALID_WRITE_MODES = {"readonly", "plan_only", "apply_allowed"}


def get_write_mode() -> str:
    mode = os.getenv("LYRA_WRITE_MODE", "plan_only").strip().lower()
    if mode not in VALID_WRITE_MODES:
        return "plan_only"
    return mode


def get_connection(timeout: float = 10.0) -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-65536")        # 64 MB page cache
    conn.execute("PRAGMA mmap_size=268435456")      # 256 MB memory-mapped I/O
    conn.execute("PRAGMA synchronous=NORMAL")       # safe + faster than FULL
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA wal_autocheckpoint=1000")  # checkpoint every ~4 MB
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_content_hash_fast(path: Path) -> str:
    filepath = Path(path)
    size = filepath.stat().st_size

    hasher = hashlib.sha256()
    hasher.update(str(size).encode("utf-8"))

    if size <= 8 * 1024 * 1024:
        with filepath.open("rb") as handle:
            hasher.update(handle.read())
        return hasher.hexdigest()

    chunk = 4 * 1024 * 1024
    with filepath.open("rb") as handle:
        hasher.update(handle.read(chunk))
        handle.seek(max(size - chunk, 0))
        hasher.update(handle.read(chunk))

    return hasher.hexdigest()


def get_track_id(content_hash: str) -> str:
    return hashlib.sha256(content_hash.encode("utf-8")).hexdigest()[:32]


def migrate() -> bool:
    write_mode = get_write_mode()
    if write_mode != "apply_allowed":
        print(f"WRITE BLOCKED: LYRA_WRITE_MODE={write_mode}. Set to apply_allowed to migrate.")
        return False

    conn = get_connection(timeout=10.0)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            track_id TEXT PRIMARY KEY,
            filepath TEXT UNIQUE,
            artist TEXT,
            title TEXT,
            album TEXT,
            year TEXT,
            genre TEXT,
            duration REAL,
            bitrate INTEGER,
            source TEXT,
            status TEXT DEFAULT 'active',
            version_type TEXT,
            confidence REAL,
            energy_level REAL,
            valence REAL,
            bpm REAL,
            content_hash TEXT,
            last_seen_at REAL,
            added_at REAL,
            created_at REAL DEFAULT (strftime('%s', 'now')),
            updated_at REAL
        )
        """
    )

    _ensure_tracks_columns(c)

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            track_id TEXT,
            model TEXT,
            dimension INTEGER,
            indexed_at REAL,
            PRIMARY KEY (track_id, model)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS enrich_cache (
            provider TEXT,
            lookup_key TEXT,
            payload_json TEXT,
            mbid TEXT,
            fetched_at REAL,
            PRIMARY KEY (provider, lookup_key)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS vibe_profiles (
            name TEXT PRIMARY KEY,
            query_json TEXT,
            created_at REAL,
            track_count INTEGER
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS vibe_tracks (
            vibe_name TEXT,
            track_id TEXT,
            position INTEGER,
            PRIMARY KEY (vibe_name, track_id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS track_scores (
            track_id TEXT PRIMARY KEY,
            energy REAL,
            valence REAL,
            tension REAL,
            density REAL,
            warmth REAL,
            movement REAL,
            space REAL,
            rawness REAL,
            complexity REAL,
            nostalgia REAL,
            scored_at REAL,
            score_version INTEGER DEFAULT 1,
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT,
            stage TEXT,
            error TEXT,
            ts REAL,
            retry_count INTEGER
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS curation_plans (
            plan_id TEXT PRIMARY KEY,
            created_at REAL,
            applied_at REAL,
            plan_json TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS acquisition_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            album TEXT,
            spotify_uri TEXT,
            priority_score REAL DEFAULT 0.0,
            play_count INTEGER DEFAULT 0,
            source TEXT,
            search_query TEXT,
            status TEXT DEFAULT 'pending',
            url TEXT,
            added_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            matched_track_id TEXT,
            FOREIGN KEY(matched_track_id) REFERENCES tracks(track_id)
        )
        """
    )
    _ensure_acquisition_queue_columns(c)
    # Canonicalize legacy completion status values.
    c.execute("UPDATE acquisition_queue SET status = 'completed' WHERE lower(status) = 'complete'")

    # Catalog-first acquisition: verified discography from MusicBrainz
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_name TEXT NOT NULL,
            artist_mbid TEXT NOT NULL,
            release_group_mbid TEXT NOT NULL,
            release_mbid TEXT,
            title TEXT NOT NULL,
            release_type TEXT,
            year INTEGER,
            track_count INTEGER,
            tracks_json TEXT,
            status TEXT DEFAULT 'pending',
            acquired_at TEXT,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_artist ON catalog_releases(artist_mbid)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_catalog_status ON catalog_releases(status)")
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_catalog_rg ON catalog_releases(release_group_mbid)"
    )

    # Phase 9-10 tables (idempotent; used by Architect/Radio/Lore engines)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            type TEXT,
            weight REAL DEFAULT 0.5,
            evidence TEXT,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_connections_source ON connections(source)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_connections_target ON connections(target)")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS track_structure (
            track_id TEXT PRIMARY KEY,
            structure_json TEXT,
            has_drop BOOLEAN DEFAULT 0,
            drop_timestamp REAL,
            bpm REAL,
            key_signature TEXT,
            energy_profile TEXT,
            analyzed_at REAL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_structure_has_drop ON track_structure(has_drop)")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS playback_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            ts REAL DEFAULT (strftime('%s', 'now')),
            context TEXT,
            session_id TEXT,
            skipped BOOLEAN DEFAULT 0,
            completion_rate REAL,
            rating INTEGER,
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_playback_track ON playback_history(track_id)")
    # Legacy schemas may use played_at (TIMESTAMP) instead of ts (REAL)
    c.execute("PRAGMA table_info(playback_history)")
    pb_cols = {row[1] for row in c.fetchall()}
    if "played_at" in pb_cols:
        c.execute("CREATE INDEX IF NOT EXISTS idx_playback_played_at ON playback_history(played_at)")
    elif "ts" in pb_cols:
        c.execute("CREATE INDEX IF NOT EXISTS idx_playback_ts ON playback_history(ts)")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS taste_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dimension TEXT NOT NULL UNIQUE,
            value REAL NOT NULL,
            confidence REAL DEFAULT 0.5,
            last_updated REAL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_taste_dimension ON taste_profile(dimension)")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            algorithm TEXT,
            added_at REAL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_queue_position ON radio_queue(position)")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sample_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            sampled_artist TEXT,
            sampled_title TEXT,
            original_artist TEXT,
            original_title TEXT,
            original_year INTEGER,
            sample_type TEXT,
            confidence REAL DEFAULT 0.5,
            source TEXT,
            verified BOOLEAN DEFAULT 0,
            created_at REAL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_sample_track ON sample_lineage(track_id)")

    # ── Spotify import tables ──────────────────────────────────
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS spotify_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT,
            track TEXT,
            album TEXT,
            played_at TEXT,
            ms_played INTEGER,
            spotify_track_uri TEXT,
            reason_start TEXT,
            reason_end TEXT,
            shuffle INTEGER,
            skipped INTEGER,
            platform TEXT,
            conn_country TEXT,
            ip_addr TEXT,
            episode_name TEXT,
            episode_show_name TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS spotify_library (
            spotify_uri TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            title TEXT NOT NULL,
            album TEXT,
            album_uri TEXT,
            artist_uri TEXT,
            duration_ms INTEGER,
            popularity INTEGER,
            explicit INTEGER,
            release_date TEXT,
            track_number INTEGER,
            disc_number INTEGER,
            isrc TEXT,
            preview_url TEXT,
            album_art_url TEXT,
            source TEXT DEFAULT 'liked',
            playlist_name TEXT,
            added_at TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS spotify_features (
            spotify_uri TEXT PRIMARY KEY,
            danceability REAL,
            energy REAL,
            key INTEGER,
            loudness REAL,
            mode INTEGER,
            speechiness REAL,
            acousticness REAL,
            instrumentalness REAL,
            liveness REAL,
            valence REAL,
            tempo REAL,
            time_signature INTEGER,
            fetched_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(spotify_uri) REFERENCES spotify_library(spotify_uri)
        )
        """
    )

    # ── All indexes ───────────────────────────────────────────
    c.execute("CREATE INDEX IF NOT EXISTS idx_tracks_filepath ON tracks(filepath)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_track ON embeddings(track_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_enrich_provider ON enrich_cache(provider)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vibe_name ON vibe_tracks(vibe_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_acq_status ON acquisition_queue(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_acq_priority ON acquisition_queue(priority_score DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON track_scores(scored_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_history_artist_track ON spotify_history(artist, track)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_history_played_at ON spotify_history(played_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_history_uri ON spotify_history(spotify_track_uri)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_library_artist_title ON spotify_library(artist, title)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_library_source ON spotify_library(source)")

    conn.commit()
    conn.close()
    return True


def _ensure_tracks_columns(cursor: sqlite3.Cursor) -> None:
    cursor.execute("PRAGMA table_info(tracks)")
    columns = {row[1] for row in cursor.fetchall()}

    desired = {
        "track_id": "TEXT",
        "filepath": "TEXT",
        "artist": "TEXT",
        "title": "TEXT",
        "album": "TEXT",
        "year": "TEXT",
        "genre": "TEXT",
        "duration": "REAL",
        "bitrate": "INTEGER",
        "source": "TEXT",
        "status": "TEXT",
        "version_type": "TEXT",
        "confidence": "REAL",
        "energy_level": "REAL",
        "valence": "REAL",
        "bpm": "REAL",
        "content_hash": "TEXT",
        "last_seen_at": "REAL",
        "added_at": "REAL",
        "created_at": "REAL",
        "updated_at": "REAL",
    }

    for name, col_type in desired.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE tracks ADD COLUMN {name} {col_type}")

    cursor.execute("SELECT track_id, filepath, content_hash FROM tracks")
    for track_id, filepath, content_hash in cursor.fetchall():
        updated = False
        new_hash = content_hash
        new_id = track_id

        if not new_hash and filepath:
            try:
                new_hash = get_content_hash_fast(Path(filepath))
                updated = True
            except Exception:
                new_hash = hashlib.sha256(str(filepath).encode("utf-8")).hexdigest()
                updated = True

        if not new_id:
            base = new_hash or hashlib.sha256(str(filepath).encode("utf-8")).hexdigest()
            new_id = get_track_id(base)
            updated = True

        if updated:
            cursor.execute(
                "UPDATE tracks SET track_id = ?, content_hash = ? WHERE filepath = ?",
                (new_id, new_hash, filepath)
            )


def _ensure_acquisition_queue_columns(cursor: sqlite3.Cursor) -> None:
    cursor.execute("PRAGMA table_info(acquisition_queue)")
    columns = {row[1] for row in cursor.fetchall()}
    desired = {
        "priority_score": "REAL DEFAULT 0.0",
        "added_at": "TEXT DEFAULT (datetime('now'))",
        "completed_at": "TEXT",
        "url": "TEXT",
        "error": "TEXT",
        "retry_count": "INTEGER DEFAULT 0",
    }
    for name, col_type in desired.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE acquisition_queue ADD COLUMN {name} {col_type}")


def _print_result(success: bool) -> None:
    if success:
        print(f"DB READY: {DB_PATH}")
    else:
        print("DB NOT MODIFIED")


if __name__ == "__main__":
    _print_result(migrate())
