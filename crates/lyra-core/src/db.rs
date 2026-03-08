use rusqlite::{params, Connection};

use crate::config::AppPaths;
use crate::errors::LyraResult;
use crate::providers::ProviderCapabilitySeed;

pub fn connect(paths: &AppPaths) -> LyraResult<Connection> {
    let conn = Connection::open(&paths.db_path)?;
    conn.execute_batch(
        "
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA temp_store = MEMORY;
        ",
    )?;
    Ok(conn)
}

pub fn init_database(conn: &Connection) -> LyraResult<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS artists (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS albums (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          artist_id INTEGER,
          title TEXT NOT NULL,
          UNIQUE(artist_id, title),
          FOREIGN KEY(artist_id) REFERENCES artists(id)
        );
        CREATE TABLE IF NOT EXISTS tracks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          legacy_track_key TEXT,
          artist_id INTEGER,
          album_id INTEGER,
          title TEXT NOT NULL,
          path TEXT NOT NULL UNIQUE,
          duration_seconds REAL NOT NULL DEFAULT 0,
          imported_at TEXT NOT NULL,
          FOREIGN KEY(artist_id) REFERENCES artists(id),
          FOREIGN KEY(album_id) REFERENCES albums(id)
        );
        CREATE TABLE IF NOT EXISTS library_roots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          path TEXT NOT NULL UNIQUE,
          added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          status TEXT NOT NULL,
          files_scanned INTEGER NOT NULL DEFAULT 0,
          tracks_imported INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL,
          finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS playlists (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS playlist_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          playlist_id INTEGER NOT NULL,
          track_id INTEGER NOT NULL,
          position INTEGER NOT NULL,
          UNIQUE(playlist_id, position),
          FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
          FOREIGN KEY(track_id) REFERENCES tracks(id)
        );
        CREATE TABLE IF NOT EXISTS queue_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          track_id INTEGER NOT NULL,
          position INTEGER NOT NULL,
          UNIQUE(position),
          FOREIGN KEY(track_id) REFERENCES tracks(id)
        );
        CREATE TABLE IF NOT EXISTS session_state (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_configs (
          provider_key TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0,
          config_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_capabilities (
          provider_key TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          capabilities_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS migration_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          status TEXT NOT NULL,
          summary_json TEXT NOT NULL,
          ran_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS track_scores (
          track_id INTEGER PRIMARY KEY,
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
          bpm REAL,
          key_signature TEXT,
          scored_at TEXT NOT NULL,
          score_version INTEGER NOT NULL DEFAULT 2,
          FOREIGN KEY(track_id) REFERENCES tracks(id)
        );
        CREATE TABLE IF NOT EXISTS taste_profile (
          dimension TEXT PRIMARY KEY,
          value REAL NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.5,
          last_updated TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS playback_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          track_id INTEGER NOT NULL,
          ts TEXT NOT NULL,
          context TEXT,
          completion_rate REAL,
          skipped INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(track_id) REFERENCES tracks(id)
        );
        CREATE TABLE IF NOT EXISTS acquisition_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          artist TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          album TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          priority_score REAL NOT NULL DEFAULT 0.0,
          source TEXT,
          added_at TEXT NOT NULL,
          completed_at TEXT,
          error TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          lifecycle_stage TEXT,
          lifecycle_progress REAL,
          lifecycle_note TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS enrich_cache (
          provider TEXT NOT NULL,
          lookup_key TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY(provider, lookup_key)
        );
        CREATE INDEX IF NOT EXISTS idx_track_scores_track ON track_scores(track_id);
        CREATE INDEX IF NOT EXISTS idx_ph_track ON playback_history(track_id);
        CREATE INDEX IF NOT EXISTS idx_ph_ts ON playback_history(ts);
        CREATE INDEX IF NOT EXISTS idx_aq_status ON acquisition_queue(status);
        CREATE INDEX IF NOT EXISTS idx_aq_priority ON acquisition_queue(priority_score DESC);
        CREATE INDEX IF NOT EXISTS idx_ec_provider ON enrich_cache(provider);
        CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(title, artist, album);
        CREATE TRIGGER IF NOT EXISTS tracks_fts_after_insert
          AFTER INSERT ON tracks
        BEGIN
          INSERT INTO tracks_fts(rowid, title, artist, album)
          VALUES (
            new.id,
            new.title,
            COALESCE((SELECT name FROM artists WHERE id = new.artist_id), ''),
            COALESCE((SELECT title FROM albums WHERE id = new.album_id), '')
          );
        END;
        CREATE TRIGGER IF NOT EXISTS tracks_fts_after_delete
          AFTER DELETE ON tracks
        BEGIN
          DELETE FROM tracks_fts WHERE rowid = old.id;
        END;
        CREATE TABLE IF NOT EXISTS curation_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action TEXT NOT NULL,
          track_ids_json TEXT NOT NULL DEFAULT '[]',
          detail TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          undone INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS playlist_track_reasons (
          playlist_id INTEGER NOT NULL,
          track_id INTEGER NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (playlist_id, track_id),
          FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
          FOREIGN KEY (track_id) REFERENCES tracks(id)
        );
        CREATE TABLE IF NOT EXISTS discovery_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          artist_name TEXT NOT NULL,
          action TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_health (
          provider_key TEXT PRIMARY KEY,
          status TEXT NOT NULL DEFAULT 'healthy',
          failure_count INTEGER NOT NULL DEFAULT 0,
          last_failure TEXT,
          last_success TEXT,
          circuit_open INTEGER NOT NULL DEFAULT 0,
          last_check TEXT NOT NULL
        );
        ",
    )?;
    // Backfill FTS index for any tracks not yet indexed
    conn.execute_batch(
        "INSERT INTO tracks_fts(rowid, title, artist, album)
         SELECT t.id, t.title, COALESCE(ar.name,''), COALESCE(al.title,'')
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE t.id NOT IN (SELECT rowid FROM tracks_fts)"
    ).unwrap_or_default();
    // Extend tracks with rich metadata columns (idempotent)
    for (col, typedef) in &[
        ("genre", "TEXT"),
        ("year", "TEXT"),
        ("artist_mbid", "TEXT"),
        ("recording_mbid", "TEXT"),
        ("content_hash", "TEXT"),
        ("last_enriched_at", "TEXT"),
        ("legacy_status", "TEXT"),
        ("bpm", "REAL"),
        ("key_signature", "TEXT"),
        ("liked_at", "TEXT"),
    ] {
        let _ = conn.execute(
            &format!("ALTER TABLE tracks ADD COLUMN {col} {typedef}"),
            [],
        );
    }
    // Extend tracks with quarantine column
    let _ = conn.execute("ALTER TABLE tracks ADD COLUMN quarantined INTEGER DEFAULT 0", []);

    for (col, typedef) in &[
        ("lifecycle_stage", "TEXT"),
        ("lifecycle_progress", "REAL"),
        ("lifecycle_note", "TEXT"),
        ("updated_at", "TEXT"),
    ] {
        let _ = conn.execute(
            &format!("ALTER TABLE acquisition_queue ADD COLUMN {col} {typedef}"),
            [],
        );
    }
    Ok(())
}

pub fn seed_provider_capabilities(
    conn: &Connection,
    seeds: &[ProviderCapabilitySeed],
) -> LyraResult<()> {
    for seed in seeds {
        conn.execute(
            "
            INSERT INTO provider_capabilities (provider_key, display_name, capabilities_json)
            VALUES (?1, ?2, ?3)
            ON CONFLICT(provider_key) DO UPDATE SET
              display_name = excluded.display_name,
              capabilities_json = excluded.capabilities_json
            ",
            params![
                seed.provider_key,
                seed.display_name,
                serde_json::to_string(&seed.capabilities)?
            ],
        )?;
    }
    Ok(())
}
