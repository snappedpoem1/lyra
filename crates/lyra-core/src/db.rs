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
          status TEXT NOT NULL DEFAULT 'active',
          duration_seconds REAL NOT NULL DEFAULT 0,
          version_type TEXT NOT NULL DEFAULT 'unknown',
          confidence REAL NOT NULL DEFAULT 0.0,
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
        CREATE TABLE IF NOT EXISTS composer_diagnostics (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          level TEXT NOT NULL,
          event_type TEXT NOT NULL,
          prompt TEXT NOT NULL,
          action TEXT,
          provider TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT '',
          message TEXT NOT NULL DEFAULT '',
          payload_json TEXT,
          created_at TEXT NOT NULL
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
          status TEXT NOT NULL DEFAULT 'queued',
          queue_position INTEGER NOT NULL DEFAULT 0,
          priority_score REAL NOT NULL DEFAULT 0.0,
          source TEXT,
          added_at TEXT NOT NULL,
          started_at TEXT,
          completed_at TEXT,
          failed_at TEXT,
          cancelled_at TEXT,
          error TEXT,
          status_message TEXT,
          failure_stage TEXT,
          failure_reason TEXT,
          failure_detail TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          selected_provider TEXT,
          selected_tier TEXT,
          worker_label TEXT,
          output_path TEXT,
          downstream_track_id INTEGER,
          scan_completed INTEGER NOT NULL DEFAULT 0,
          organize_completed INTEGER NOT NULL DEFAULT 0,
          index_completed INTEGER NOT NULL DEFAULT 0,
          cancel_requested INTEGER NOT NULL DEFAULT 0,
          lifecycle_stage TEXT,
          lifecycle_progress REAL,
          lifecycle_note TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS acquisition_plans (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL CHECK(kind IN ('single_track', 'album', 'discography')),
          status TEXT NOT NULL CHECK(status IN ('queued', 'partial', 'blocked')),
          source TEXT,
          requested_artist TEXT,
          requested_title TEXT,
          requested_album TEXT,
          canonical_artist TEXT,
          canonical_album TEXT,
          summary TEXT NOT NULL DEFAULT '',
          total_items INTEGER NOT NULL DEFAULT 0,
          queued_items INTEGER NOT NULL DEFAULT 0,
          blocked_items INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS acquisition_plan_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          plan_id INTEGER NOT NULL,
          item_kind TEXT NOT NULL CHECK(item_kind IN ('single_track', 'album_track', 'discography_track')),
          status TEXT NOT NULL CHECK(status IN ('queued', 'duplicate_owned', 'already_queued', 'rejected')),
          artist TEXT NOT NULL,
          title TEXT NOT NULL,
          album TEXT,
          release_group_mbid TEXT,
          release_date TEXT,
          disc_number INTEGER,
          track_number INTEGER,
          queue_item_id INTEGER,
          evidence_level TEXT NOT NULL DEFAULT 'provider_metadata',
          evidence_summary TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          UNIQUE(plan_id, artist, title, album, disc_number, track_number),
          FOREIGN KEY(plan_id) REFERENCES acquisition_plans(id) ON DELETE CASCADE,
          FOREIGN KEY(queue_item_id) REFERENCES acquisition_queue(id)
        );
        CREATE TABLE IF NOT EXISTS enrich_cache (
          provider TEXT NOT NULL,
          lookup_key TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY(provider, lookup_key)
        );
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
        );
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
        );
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
        );
        CREATE INDEX IF NOT EXISTS idx_track_scores_track ON track_scores(track_id);
        CREATE INDEX IF NOT EXISTS idx_ph_track ON playback_history(track_id);
        CREATE INDEX IF NOT EXISTS idx_ph_ts ON playback_history(ts);
        CREATE INDEX IF NOT EXISTS idx_aq_status ON acquisition_queue(status);
        CREATE INDEX IF NOT EXISTS idx_aq_priority ON acquisition_queue(priority_score DESC);
        CREATE INDEX IF NOT EXISTS idx_ap_kind ON acquisition_plans(kind);
        CREATE INDEX IF NOT EXISTS idx_ap_status ON acquisition_plans(status);
        CREATE INDEX IF NOT EXISTS idx_api_plan_id ON acquisition_plan_items(plan_id);
        CREATE INDEX IF NOT EXISTS idx_api_status ON acquisition_plan_items(status);
        CREATE INDEX IF NOT EXISTS idx_ec_provider ON enrich_cache(provider);
        CREATE INDEX IF NOT EXISTS idx_history_artist_track ON spotify_history(artist, track);
        CREATE INDEX IF NOT EXISTS idx_history_played_at ON spotify_history(played_at);
        CREATE INDEX IF NOT EXISTS idx_history_uri ON spotify_history(spotify_track_uri);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_history_dedup
            ON spotify_history(artist, track, played_at, ms_played, spotify_track_uri);
        CREATE INDEX IF NOT EXISTS idx_library_artist_title ON spotify_library(artist, title);
        CREATE INDEX IF NOT EXISTS idx_library_source ON spotify_library(source);
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
          reason_json TEXT,
          phase_key TEXT,
          phase_label TEXT,
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
        CREATE TABLE IF NOT EXISTS composer_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          prompt TEXT NOT NULL,
          action TEXT NOT NULL,
          active_role TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          provider TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT '',
          response_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS connections (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          target TEXT NOT NULL,
          type TEXT NOT NULL,
          weight REAL NOT NULL DEFAULT 0.5,
          evidence TEXT,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_connections_source ON connections(source);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_connections_pair ON connections(source, target, type);
        CREATE TABLE IF NOT EXISTS artist_lineage_edges (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_artist TEXT NOT NULL,
          target_artist TEXT NOT NULL,
          relationship_type TEXT NOT NULL CHECK(relationship_type IN ('shared_member', 'side_project', 'offshoot', 'member_of', 'influence')),
          evidence_level TEXT NOT NULL CHECK(evidence_level IN ('verified', 'curated', 'inferred', 'unavailable')),
          weight REAL NOT NULL DEFAULT 0.5,
          evidence_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL,
          UNIQUE(source_artist, target_artist, relationship_type)
        );
        CREATE INDEX IF NOT EXISTS idx_artist_lineage_source ON artist_lineage_edges(source_artist);
        CREATE TABLE IF NOT EXISTS provider_health (
          provider_key TEXT PRIMARY KEY,
          status TEXT NOT NULL DEFAULT 'healthy',
          failure_count INTEGER NOT NULL DEFAULT 0,
          last_failure TEXT,
          last_success TEXT,
          circuit_open INTEGER NOT NULL DEFAULT 0,
          last_check TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS track_validation (
          track_id INTEGER PRIMARY KEY,
          status TEXT NOT NULL,
          confidence REAL,
          source TEXT,
          validated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tv_status ON track_validation(status);
        CREATE TABLE IF NOT EXISTS provider_catalog_tracks (
          provider TEXT NOT NULL,
          provider_track_id TEXT NOT NULL,
          artist_name TEXT NOT NULL,
          artist_normalized TEXT NOT NULL CHECK(trim(artist_normalized) != ''),
          title TEXT NOT NULL,
          title_normalized TEXT NOT NULL CHECK(trim(title_normalized) != ''),
          album_title TEXT,
          album_normalized TEXT,
          isrc TEXT CHECK(isrc IS NULL OR length(isrc) = 12),
          duration_ms INTEGER CHECK(duration_ms IS NULL OR duration_ms >= 0),
          popularity INTEGER CHECK(popularity IS NULL OR (popularity >= 0 AND popularity <= 100)),
          explicit INTEGER NOT NULL DEFAULT 0 CHECK(explicit IN (0, 1)),
          version_type TEXT NOT NULL CHECK(version_type IN ('original', 'remix', 'live', 'cover', 'junk', 'special', 'unknown')),
          source_kind TEXT NOT NULL CHECK(source_kind IN ('library', 'history', 'recommendation', 'enrichment', 'acquisition')),
          payload_json TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY(provider, provider_track_id)
        ) STRICT;
        CREATE INDEX IF NOT EXISTS idx_provider_catalog_track_names
          ON provider_catalog_tracks(artist_normalized, title_normalized);
        CREATE INDEX IF NOT EXISTS idx_provider_catalog_track_isrc
          ON provider_catalog_tracks(isrc);
        CREATE TABLE IF NOT EXISTS provider_oauth_sessions (
          provider_key TEXT PRIMARY KEY,
          token_type TEXT NOT NULL DEFAULT 'Bearer',
          scope TEXT NOT NULL DEFAULT '',
          access_token_expires_at TEXT,
          refreshed_at TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS provider_auth_flows (
          provider_key TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          redirect_uri TEXT NOT NULL,
          scope TEXT NOT NULL DEFAULT '',
          expires_at TEXT NOT NULL,
          completed_at TEXT
        ) STRICT;
        CREATE TABLE IF NOT EXISTS track_audio_features (
          track_id INTEGER PRIMARY KEY,
          tag_bpm REAL,
          tag_key TEXT,
          rms_energy REAL,
          peak_amplitude REAL,
          dynamic_range REAL,
          energy_volatility REAL,
          has_high_volatility INTEGER,
          is_loud INTEGER,
          is_dynamic INTEGER,
          extracted_at TEXT NOT NULL,
          extraction_method TEXT NOT NULL DEFAULT 'none',
          FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_taf_track ON track_audio_features(track_id);
        CREATE TABLE IF NOT EXISTS taste_memory_preferences (
          axis_key TEXT PRIMARY KEY,
          axis_label TEXT NOT NULL,
          preferred_pole TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.0,
          evidence_count INTEGER NOT NULL DEFAULT 0,
          last_seen_at TEXT NOT NULL,
          supporting_phrases_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS taste_route_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action TEXT NOT NULL,
          route_kind TEXT NOT NULL,
          source TEXT NOT NULL,
          outcome TEXT NOT NULL DEFAULT 'observed',
          note TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.0,
          observed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_taste_route_history_observed ON taste_route_history(observed_at DESC);
        CREATE TABLE IF NOT EXISTS lineage_ingest_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_at TEXT NOT NULL,
          artists_processed INTEGER NOT NULL DEFAULT 0,
          edges_inserted INTEGER NOT NULL DEFAULT 0,
          artists_skipped INTEGER NOT NULL DEFAULT 0,
          error_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_lineage_ingest_log_run_at ON lineage_ingest_log(run_at DESC);
        CREATE TABLE IF NOT EXISTS audio_extraction_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_at TEXT NOT NULL,
          tracks_processed INTEGER NOT NULL DEFAULT 0,
          tracks_succeeded INTEGER NOT NULL DEFAULT 0,
          tracks_failed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_audio_extraction_log_run_at ON audio_extraction_log(run_at DESC);
        ",
    )?;
    // Backfill FTS index for any tracks not yet indexed
    conn.execute_batch(
        "INSERT INTO tracks_fts(rowid, title, artist, album)
         SELECT t.id, t.title, COALESCE(ar.name,''), COALESCE(al.title,'')
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE t.id NOT IN (SELECT rowid FROM tracks_fts)",
    )
    .unwrap_or_default();
    // Extend tracks with rich metadata columns (idempotent)
    for (col, typedef) in &[
        (
            "status",
            "TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'quarantined', 'hidden'))",
        ),
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
        (
            "version_type",
            "TEXT NOT NULL DEFAULT 'unknown' CHECK(version_type IN ('original', 'remix', 'live', 'cover', 'junk', 'special', 'unknown'))",
        ),
        (
            "confidence",
            "REAL NOT NULL DEFAULT 0.0 CHECK(confidence >= 0.0 AND confidence <= 1.0)",
        ),
        ("track_number", "INTEGER"),
        ("disc_number", "INTEGER"),
    ] {
        let _ = conn.execute(
            &format!("ALTER TABLE tracks ADD COLUMN {col} {typedef}"),
            [],
        );
    }
    // Extend tracks with quarantine column
    let _ = conn.execute(
        "ALTER TABLE tracks ADD COLUMN quarantined INTEGER DEFAULT 0",
        [],
    );
    let _ = conn.execute(
        "UPDATE tracks SET status = 'active' WHERE status IS NULL OR trim(status) = ''",
        [],
    );
    let _ = conn.execute(
        "UPDATE tracks SET version_type = 'unknown' WHERE version_type IS NULL OR trim(version_type) = ''",
        [],
    );
    let _ = conn.execute(
        "UPDATE tracks SET confidence = 0.0 WHERE confidence IS NULL",
        [],
    );

    for (col, typedef) in &[
        ("queue_position", "INTEGER NOT NULL DEFAULT 0"),
        ("started_at", "TEXT"),
        ("failed_at", "TEXT"),
        ("cancelled_at", "TEXT"),
        ("status_message", "TEXT"),
        ("failure_stage", "TEXT"),
        ("failure_reason", "TEXT"),
        ("failure_detail", "TEXT"),
        ("selected_provider", "TEXT"),
        ("selected_tier", "TEXT"),
        ("worker_label", "TEXT"),
        ("validation_confidence", "REAL"),
        ("validation_summary", "TEXT"),
        ("target_root_id", "INTEGER"),
        ("target_root_path", "TEXT"),
        ("output_path", "TEXT"),
        ("downstream_track_id", "INTEGER"),
        ("scan_completed", "INTEGER NOT NULL DEFAULT 0"),
        ("organize_completed", "INTEGER NOT NULL DEFAULT 0"),
        ("index_completed", "INTEGER NOT NULL DEFAULT 0"),
        ("cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
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
    let _ = conn.execute(
        "UPDATE acquisition_queue SET status = 'queued' WHERE status = 'pending'",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue SET status = 'acquiring' WHERE status = 'in_progress'",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue SET status = 'cancelled' WHERE status = 'skipped'",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue
         SET queue_position = id
         WHERE queue_position IS NULL OR queue_position = 0",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue
         SET status_message = COALESCE(status_message, lifecycle_note)
         WHERE status_message IS NULL AND lifecycle_note IS NOT NULL",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue
         SET failed_at = COALESCE(failed_at, completed_at)
         WHERE status = 'failed' AND failed_at IS NULL",
        [],
    );
    let _ = conn.execute(
        "UPDATE acquisition_queue
         SET cancelled_at = COALESCE(cancelled_at, completed_at)
         WHERE status = 'cancelled' AND cancelled_at IS NULL",
        [],
    );
    for (col, typedef) in &[
        ("reason_json", "TEXT"),
        ("phase_key", "TEXT"),
        ("phase_label", "TEXT"),
    ] {
        let _ = conn.execute(
            &format!("ALTER TABLE playlist_track_reasons ADD COLUMN {col} {typedef}"),
            [],
        );
    }
    let _ = conn.execute(
        "ALTER TABLE taste_route_history ADD COLUMN outcome TEXT NOT NULL DEFAULT 'observed'",
        [],
    );
    let _ = conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_composer_diagnostics_created_at ON composer_diagnostics(created_at DESC)",
        [],
    );
    let _ = conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_composer_runs_created_at ON composer_runs(created_at DESC)",
        [],
    );
    for (col, typedef) in &[
        ("active_role", "TEXT NOT NULL DEFAULT ''"),
        ("summary", "TEXT NOT NULL DEFAULT ''"),
        ("provider", "TEXT NOT NULL DEFAULT ''"),
        ("mode", "TEXT NOT NULL DEFAULT ''"),
        ("response_json", "TEXT"),
    ] {
        let _ = conn.execute(
            &format!("ALTER TABLE composer_runs ADD COLUMN {col} {typedef}"),
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
