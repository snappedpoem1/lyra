pub mod acquisition;
pub mod acquisition_dispatcher;
pub mod acquisition_worker;
pub mod commands;
pub mod config;
pub mod db;
pub mod diagnostics;
pub mod enrichment;
pub mod errors;
pub mod library;
pub mod logging;
pub mod native;
pub mod oracle;
pub mod playback;
pub mod playlists;
pub mod providers;
pub mod queue;
pub mod scores;
pub mod scrobble;
pub mod state;
pub mod taste;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use chrono::Utc;
use commands::{
    AcquisitionQueueItem, AudioOutputDevice, BootstrapPayload, DuplicateCluster, ExplainPayload,
    LegacyImportReport, LibraryOverview, LibraryRootRecord, NativeCapabilities, PlaybackEvent,
    PlaybackState, PlaylistDetail, PlaylistSummary, ProviderConfigRecord, ProviderHealth,
    ProviderValidationResult, QueueItemRecord, RecommendationResult, ScanJobRecord, SettingsPayload,
    TasteProfile, TrackDetail, TrackRecord, TrackScores,
};
use config::AppPaths;
use db::{connect, init_database};
use errors::{LyraError, LyraResult};
use playback::PlaybackController;
use providers::default_provider_capabilities;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};

#[derive(Clone)]
pub struct LyraCore {
    paths: AppPaths,
    playback: Arc<Mutex<PlaybackController>>,
}

impl LyraCore {
    pub fn new(app_data_dir: PathBuf) -> LyraResult<Self> {
        let paths = AppPaths::new(app_data_dir)?;
        let conn = connect(&paths)?;
        init_database(&conn)?;
        db::seed_provider_capabilities(&conn, &default_provider_capabilities())?;
        let mut session = state::load_session_state(&conn)?;
        let settings = state::load_settings(&conn)?;

        // Normalize session playback on startup.
        if settings.restore_session {
            // Keep queue/track/position but never auto-play on relaunch.
            if session.playback.status == "playing" {
                session.playback.status = "paused".to_string();
                state::save_playback_state(&conn, &session.playback)?;
            }
        } else {
            // restore_session disabled: reset to a blank idle state,
            // preserving only the volume preference.
            let volume = session.playback.volume;
            session.playback = PlaybackState {
                status: "idle".to_string(),
                current_track_id: None,
                current_track: None,
                queue_index: 0,
                position_seconds: 0.0,
                duration_seconds: 0.0,
                volume,
                shuffle: false,
                repeat_mode: "off".to_string(),
                seek_supported: false,
            };
            state::save_playback_state(&conn, &session.playback)?;
        }

        // Respect the persisted preferred output device if one is set.
        let mut controller = PlaybackController::new(session.playback.clone())?;
        if let Some(device) = settings.preferred_output_device.clone() {
            controller.set_output_device(Some(device));
        }
        Ok(Self {
            paths,
            playback: Arc::new(Mutex::new(controller)),
        })
    }

    pub fn paths(&self) -> &AppPaths {
        &self.paths
    }

    fn conn(&self) -> LyraResult<rusqlite::Connection> {
        connect(&self.paths)
    }

    pub fn bootstrap_app(&self) -> LyraResult<BootstrapPayload> {
        Ok(BootstrapPayload {
            shell: self.get_app_shell_state()?,
            native_capabilities: self.get_native_capabilities(),
        })
    }

    pub fn get_app_shell_state(&self) -> LyraResult<commands::AppShellState> {
        let conn = self.conn()?;
        Ok(commands::AppShellState {
            library_overview: self.get_library_overview()?,
            library_roots: self.list_library_roots()?,
            playlists: self.list_playlists()?,
            queue: self.get_queue()?,
            playback: self.get_playback_state()?,
            settings: self.get_settings()?,
            providers: self.list_provider_configs()?,
            scan_jobs: self.get_scan_jobs()?,
            taste_profile: taste::get_taste_profile(&conn).unwrap_or_default(),
            acquisition_queue_pending: acquisition::pending_count(&conn),
        })
    }

    pub fn list_tracks(&self, query: Option<String>) -> LyraResult<Vec<TrackRecord>> {
        let conn = self.conn()?;
        library::list_tracks(&conn, query)
    }

    pub fn list_liked_tracks(&self) -> LyraResult<Vec<TrackRecord>> {
        let conn = self.conn()?;
        library::list_liked_tracks(&conn)
    }

    pub fn toggle_like(&self, track_id: i64) -> LyraResult<bool> {
        let conn = self.conn()?;
        library::toggle_like(&conn, track_id)
    }

    pub fn get_library_overview(&self) -> LyraResult<LibraryOverview> {
        let conn = self.conn()?;
        library::get_library_overview(&conn)
    }

    pub fn list_library_roots(&self) -> LyraResult<Vec<LibraryRootRecord>> {
        let conn = self.conn()?;
        library::list_library_roots(&conn)
    }

    pub fn add_library_root(&self, path: String) -> LyraResult<Vec<LibraryRootRecord>> {
        let conn = self.conn()?;
        library::add_library_root(&conn, &PathBuf::from(path))?;
        self.list_library_roots()
    }

    pub fn remove_library_root(&self, root_id: i64) -> LyraResult<Vec<LibraryRootRecord>> {
        let conn = self.conn()?;
        library::remove_library_root(&conn, root_id)?;
        self.list_library_roots()
    }

    pub fn create_scan_job(&self) -> LyraResult<ScanJobRecord> {
        let conn = self.conn()?;
        library::create_scan_job(&conn)
    }

    pub fn get_scan_jobs(&self) -> LyraResult<Vec<ScanJobRecord>> {
        let conn = self.conn()?;
        library::get_scan_jobs(&conn)
    }

    pub fn run_scan_job<F>(&self, job_id: i64, mut notify: F) -> LyraResult<()>
    where
        F: FnMut(&str, Value) + Send + 'static,
    {
        let conn = self.conn()?;
        let roots = library::list_library_roots(&conn)?;
        library::update_scan_job_status(&conn, job_id, "running", 0, 0)?;
        let mut scanned = 0_i64;
        let mut imported = 0_i64;
        for root in roots {
            let path = PathBuf::from(&root.path);
            if !path.exists() {
                continue;
            }
            for entry in walkdir::WalkDir::new(&path)
                .into_iter()
                .filter_map(Result::ok)
                .filter(|entry| entry.file_type().is_file())
            {
                scanned += 1;
                if library::is_supported_audio_file(entry.path()) &&
                    library::import_track_from_path(&conn, entry.path())? {
                        imported += 1;
                }
                if scanned % 10 == 0 {
                    library::update_scan_job_status(&conn, job_id, "running", scanned, imported)?;
                    notify(
                        "lyra://scan-progress",
                        json!({
                            "jobId": job_id,
                            "status": "running",
                            "filesScanned": scanned,
                            "tracksImported": imported,
                        }),
                    );
                }
            }
        }
        library::update_scan_job_status(&conn, job_id, "completed", scanned, imported)?;
        notify(
            "lyra://scan-progress",
            json!({
                "jobId": job_id,
                "status": "completed",
                "filesScanned": scanned,
                "tracksImported": imported,
            }),
        );
        notify(
            "lyra://library-updated",
            json!(self.get_library_overview()?),
        );
        Ok(())
    }

    pub fn list_playlists(&self) -> LyraResult<Vec<PlaylistSummary>> {
        let conn = self.conn()?;
        playlists::list_playlists(&conn)
    }

    pub fn get_playlist_detail(&self, playlist_id: i64) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        playlists::get_playlist_detail(&conn, playlist_id)
    }

    pub fn create_playlist(&self, name: String) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        let playlist_id = playlists::create_playlist(&conn, &name)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn rename_playlist(&self, playlist_id: i64, name: String) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        playlists::rename_playlist(&conn, playlist_id, &name)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn delete_playlist(&self, playlist_id: i64) -> LyraResult<Vec<PlaylistSummary>> {
        let conn = self.conn()?;
        playlists::delete_playlist(&conn, playlist_id)?;
        self.list_playlists()
    }

    pub fn add_track_to_playlist(
        &self,
        playlist_id: i64,
        track_id: i64,
    ) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        playlists::add_track_to_playlist(&conn, playlist_id, track_id)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn remove_track_from_playlist(
        &self,
        playlist_id: i64,
        track_id: i64,
    ) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        playlists::remove_track_from_playlist(&conn, playlist_id, track_id)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn reorder_playlist_item(
        &self,
        playlist_id: i64,
        track_id: i64,
        new_position: i64,
    ) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        playlists::reorder_playlist_item(&conn, playlist_id, track_id, new_position)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn create_playlist_from_queue(&self, name: String) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        let playlist_id = playlists::create_playlist_from_queue(&conn, &name)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn playback_finished(&self) -> bool {
        self.playback
            .lock()
            .map(|c| c.is_finished())
            .unwrap_or(false)
    }

    pub fn enqueue_playlist(&self, playlist_id: i64) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        let track_ids = playlists::playlist_track_ids(&conn, playlist_id)?;
        queue::enqueue_tracks(&conn, &track_ids)?;
        self.get_queue()
    }

    pub fn enqueue_tracks(&self, track_ids: Vec<i64>) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        queue::enqueue_tracks(&conn, &track_ids)?;
        self.get_queue()
    }

    pub fn get_queue(&self) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        queue::get_queue(&conn)
    }

    pub fn move_queue_item(
        &self,
        queue_item_id: i64,
        new_position: i64,
    ) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        queue::move_queue_item(&conn, queue_item_id, new_position)?;
        self.get_queue()
    }

    pub fn remove_queue_item(&self, queue_item_id: i64) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        queue::remove_queue_item(&conn, queue_item_id)?;
        self.get_queue()
    }

    pub fn clear_queue(&self) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        queue::clear_queue(&conn)?;
        state::save_playback_state(&conn, &self.get_playback_state()?)?;
        Ok(Vec::new())
    }

    pub fn get_playback_state(&self) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let playback_state = state::load_playback_state(&conn)?;
        let controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        Ok(controller.snapshot(playback_state))
    }

    pub fn play_track(&self, track_id: i64) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        queue::ensure_track_in_queue(&conn, track_id)?;
        let track =
            library::get_track_by_id(&conn, track_id)?.ok_or(LyraError::NotFound("track"))?;
        // Fire Last.fm Now Playing in background — no-op if session_key absent.
        {
            let artist = track.artist.clone();
            let title = track.title.clone();
            let album = track.album.clone();
            let duration_secs = track.duration_seconds as u64;
            if let Ok(c2) = self.conn() {
                std::thread::spawn(move || {
                    scrobble::now_playing(&c2, &artist, &title, &album, duration_secs);
                });
            }
        }
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let next = controller.play_track(track, current.volume)?;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    pub fn play_queue_index(&self, index: i64) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let queue_items = queue::get_queue(&conn)?;
        let item = queue_items
            .get(index as usize)
            .ok_or(LyraError::InvalidInput("queue index out of range"))?;
        self.play_track(item.track_id)
    }

    pub fn toggle_playback(&self) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;

        // Cold resume: audio engine has no active track (e.g. after session restore)
        // but session state shows a paused track.  Load and start it, then seek
        // to the saved position so playback resumes from where it left off.
        if current.status == "paused" && !controller.has_active_track() {
            if let Some(track_id) = current.current_track_id {
                if let Some(track) = library::get_track_by_id(&conn, track_id)? {
                    let saved_pos = current.position_seconds;
                    let queue_index = current.queue_index;
                    let shuffle = current.shuffle;
                    let repeat_mode = current.repeat_mode.clone();
                    let mut next = controller.play_track(track, current.volume)?;
                    if saved_pos > 0.5 {
                        next = controller.seek_to(next, saved_pos)?;
                    }
                    next.queue_index = queue_index;
                    next.shuffle = shuffle;
                    next.repeat_mode = repeat_mode;
                    state::save_playback_state(&conn, &next)?;
                    return Ok(next);
                }
            }
        }

        let next = controller.toggle(current)?;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    /// Transition to "stopped" and persist so the ticker does not loop.
    pub fn stop_playback(&self) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let mut current = state::load_playback_state(&conn)?;
        current.status = "stopped".to_string();
        state::save_playback_state(&conn, &current)?;
        Ok(current)
    }

    /// Persist the live playback position to SQLite for accurate session restore.
    pub fn sync_playback_state(&self) -> LyraResult<()> {
        let conn = self.conn()?;
        let live = self.get_playback_state()?;
        state::save_playback_state(&conn, &live)?;
        Ok(())
    }

    pub fn play_next(&self) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let queue_items = queue::get_queue(&conn)?;
        let current = state::load_playback_state(&conn)?;
        let queue_len = queue_items.len();

        let (chosen_index, item) = if current.shuffle && queue_len > 1 {
            // Pick a random index different from the current one.
            use std::time::{SystemTime, UNIX_EPOCH};
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .subsec_nanos() as usize;
            let candidate = nanos % queue_len;
            let idx = if candidate == current.queue_index as usize {
                (candidate + 1) % queue_len
            } else {
                candidate
            };
            let item = queue_items
                .get(idx)
                .ok_or(LyraError::InvalidInput("queue is empty"))?;
            (idx as i64, item)
        } else {
            let next_index = current.queue_index.saturating_add(1);
            let fallback = current.queue_index;
            let (idx, item) = if queue_items.get(next_index as usize).is_some() {
                (next_index, &queue_items[next_index as usize])
            } else {
                (0.max(fallback), queue_items.first().ok_or(LyraError::InvalidInput("queue is empty"))?)
            };
            (idx, item)
        };

        let track =
            library::get_track_by_id(&conn, item.track_id)?.ok_or(LyraError::NotFound("track"))?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let mut next = controller.play_track(track, current.volume)?;
        next.queue_index = chosen_index;
        next.shuffle = current.shuffle;
        next.repeat_mode = current.repeat_mode;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    pub fn play_previous(&self) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let queue_items = queue::get_queue(&conn)?;
        let current = state::load_playback_state(&conn)?;
        let prev_index = if current.queue_index <= 0 {
            0
        } else {
            current.queue_index - 1
        };
        let item = queue_items
            .get(prev_index as usize)
            .ok_or(LyraError::InvalidInput("queue is empty"))?;
        let track =
            library::get_track_by_id(&conn, item.track_id)?.ok_or(LyraError::NotFound("track"))?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let mut next = controller.play_track(track, current.volume)?;
        next.queue_index = prev_index;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    pub fn seek_to(&self, position_seconds: f64) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let next = controller.seek_to(current, position_seconds)?;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    pub fn set_volume(&self, volume: f64) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let next = controller.set_volume(current, volume)?;
        state::save_playback_state(&conn, &next)?;
        Ok(next)
    }

    pub fn set_repeat_mode(&self, repeat_mode: String) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let mut current = state::load_playback_state(&conn)?;
        current.repeat_mode = repeat_mode;
        state::save_playback_state(&conn, &current)?;
        Ok(current)
    }

    pub fn set_shuffle(&self, shuffle: bool) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let mut current = state::load_playback_state(&conn)?;
        current.shuffle = shuffle;
        state::save_playback_state(&conn, &current)?;
        Ok(current)
    }

    pub fn get_settings(&self) -> LyraResult<SettingsPayload> {
        let conn = self.conn()?;
        state::load_settings(&conn)
    }

    pub fn update_settings(&self, settings: SettingsPayload) -> LyraResult<SettingsPayload> {
        let conn = self.conn()?;
        state::save_settings(&conn, &settings)?;
        Ok(settings)
    }

    /// List all available audio output devices on the host.
    pub fn list_audio_devices(&self) -> Vec<AudioOutputDevice> {
        playback::enumerate_output_devices()
    }

    /// Switch the preferred output device.  Persists the preference in
    /// settings.  The caller should re-issue play after switching if a track
    /// was already playing.
    pub fn set_output_device(&self, device_name: Option<String>) -> LyraResult<SettingsPayload> {
        let conn = self.conn()?;
        let mut settings = state::load_settings(&conn)?;
        settings.preferred_output_device = device_name.clone();
        state::save_settings(&conn, &settings)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        controller.set_output_device(device_name);
        Ok(settings)
    }

    pub fn list_provider_configs(&self) -> LyraResult<Vec<ProviderConfigRecord>> {
        let conn = self.conn()?;
        providers::list_provider_configs(&conn)
    }

    pub fn update_provider_config(
        &self,
        provider_key: String,
        enabled: bool,
        values: Value,
    ) -> LyraResult<Vec<ProviderConfigRecord>> {
        let conn = self.conn()?;
        providers::update_provider_config(&conn, &provider_key, enabled, &values)?;
        self.list_provider_configs()
    }

    pub fn list_provider_health(&self) -> LyraResult<Vec<ProviderHealth>> {
        let conn = self.conn()?;
        providers::list_provider_health(&conn)
    }

    pub fn get_provider_health(&self, provider_key: String) -> LyraResult<ProviderHealth> {
        let conn = self.conn()?;
        providers::get_provider_health(&conn, &provider_key)
    }

    pub fn record_provider_event(
        &self,
        provider_key: String,
        success: bool,
    ) -> LyraResult<ProviderHealth> {
        let conn = self.conn()?;
        if success {
            providers::record_provider_success(&conn, &provider_key)?;
            providers::get_provider_health(&conn, &provider_key)
        } else {
            providers::record_provider_failure(&conn, &provider_key)
        }
    }

    pub fn reset_provider_health(&self, provider_key: String) -> LyraResult<Vec<ProviderHealth>> {
        let conn = self.conn()?;
        providers::reset_provider_health(&conn, &provider_key)?;
        providers::list_provider_health(&conn)
    }

    pub fn validate_provider(
        &self,
        provider_key: String,
    ) -> LyraResult<ProviderValidationResult> {
        let conn = self.conn()?;
        providers::validate_provider(&conn, &provider_key)
    }

    /// Save a provider secret to the OS keychain.
    pub fn keyring_save(
        &self,
        provider_key: String,
        key_name: String,
        secret: String,
    ) -> Result<(), String> {
        providers::keyring_save(&provider_key, &key_name, &secret)
    }

    /// Load a provider secret from the OS keychain.
    pub fn keyring_load(
        &self,
        provider_key: String,
        key_name: String,
    ) -> Result<Option<String>, String> {
        providers::keyring_load(&provider_key, &key_name)
    }

    /// Delete a provider secret from the OS keychain.
    pub fn keyring_delete(
        &self,
        provider_key: String,
        key_name: String,
    ) -> Result<(), String> {
        providers::keyring_delete(&provider_key, &key_name)
    }

    /// Scan a `.env` file and save all credential-like values to the OS keychain.
    /// Returns (saved_count, skipped_count).
    pub fn backup_env_to_keychain(&self, env_path: String) -> Result<(usize, usize), String> {
        providers::backup_env_to_keychain(&env_path)
    }

    /// Load a single env credential from the keychain (stored as env:{KEY_NAME}).
    pub fn load_env_credential(&self, key_name: String) -> Result<Option<String>, String> {
        providers::load_env_credential(&key_name)
    }

    /// Authenticate Last.fm with username/password to obtain a session key.
    /// The session key is stored in the lastfm provider config automatically.
    pub fn lastfm_get_session(
        &self,
        api_key: String,
        api_secret: String,
        username: String,
        password: String,
    ) -> Result<String, String> {
        let conn = self.conn().map_err(|e| e.to_string())?;
        providers::lastfm_get_session(&conn, &api_key, &api_secret, &username, &password)
    }

    pub fn find_duplicates(&self) -> LyraResult<Vec<DuplicateCluster>> {
        let conn = self.conn()?;
        library::find_duplicates(&conn)
    }

    pub fn run_legacy_import(
        &self,
        env_path: Option<String>,
        legacy_db_path: Option<String>,
    ) -> LyraResult<LegacyImportReport> {
        let conn = self.conn()?;
        let mut imported = Vec::new();
        let mut unsupported = Vec::new();
        let mut notes = Vec::new();

        let env_source = env_path.map(PathBuf::from).or_else(|| {
            let candidate = PathBuf::from(".env");
            candidate.exists().then_some(candidate)
        });
        if let Some(env_file) = env_source {
            let imported_count =
                providers::import_env_file(&conn, &env_file, &mut imported, &mut unsupported)?;
            notes.push(format!(
                "Imported {imported_count} supported provider settings from {}",
                env_file.display()
            ));
        } else {
            notes.push("No .env source found for provider import".to_string());
        }

        let db_source = legacy_db_path.map(PathBuf::from).or_else(|| {
            let candidate = PathBuf::from("lyra_registry.db");
            candidate.exists().then_some(candidate)
        });
        if let Some(db_file) = db_source {
            let imported_tracks = self.import_legacy_database(&conn, &db_file)?;
            imported.push(format!("tracks:{imported_tracks}"));
            notes.push(format!(
                "Imported legacy database content from {}",
                db_file.display()
            ));
        } else {
            notes.push("No legacy SQLite database found".to_string());
        }

        conn.execute(
            "INSERT INTO migration_runs (source, status, summary_json, ran_at) VALUES (?1, ?2, ?3, ?4)",
            params![
                "legacy_import",
                "completed",
                serde_json::to_string(&json!({
                    "imported": imported,
                    "unsupported": unsupported,
                    "notes": notes,
                }))?,
                Utc::now().to_rfc3339(),
            ],
        )?;

        Ok(LegacyImportReport {
            imported,
            unsupported,
            notes,
        })
    }

    fn import_legacy_database(
        &self,
        conn: &rusqlite::Connection,
        legacy_db_path: &Path,
    ) -> LyraResult<usize> {
        if !legacy_db_path.exists() {
            return Ok(0);
        }
        let legacy = rusqlite::Connection::open(legacy_db_path)?;
        let mut imported_tracks = 0_usize;

        let tables = [
            "tracks",
            "saved_playlists",
            "saved_playlist_tracks",
            "player_queue",
            "player_state",
            "track_scores",
            "taste_profile",
            "acquisition_queue",
            "enrich_cache",
            "playback_history",
            "vibe_profiles",
            "spotify_history",
        ];
        for table in tables {
            let exists = legacy
                .query_row(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?1",
                    params![table],
                    |_| Ok(1_i64),
                )
                .optional()?;
            if exists.is_none() {
                continue;
            }
            match table {
                "tracks" => {
                    let mut stmt = legacy.prepare(
                        "SELECT filepath, title, artist, album, duration FROM tracks WHERE filepath IS NOT NULL",
                    )?;
                    let rows = stmt.query_map([], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                            row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                            row.get::<_, Option<String>>(3)?.unwrap_or_default(),
                            row.get::<_, Option<f64>>(4)?.unwrap_or(0.0),
                        ))
                    })?;
                    for row in rows {
                        let (filepath, title, artist, album, duration) = row?;
                        imported_tracks += usize::from(library::import_legacy_track(
                            conn, &filepath, &title, &artist, &album, duration,
                        )?);
                    }
                }
                "saved_playlists" => {
                    let mut stmt =
                        legacy.prepare("SELECT id, name, description FROM saved_playlists")?;
                    let rows = stmt.query_map([], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                        ))
                    })?;
                    for row in rows {
                        let (_legacy_id, name, description) = row?;
                        let playlist_id = playlists::ensure_playlist(conn, &name, &description)?;
                        let _ = playlist_id;
                    }
                }
                "saved_playlist_tracks" => {
                    let mut stmt = legacy.prepare(
                        "SELECT playlist_id, track_id, position FROM saved_playlist_tracks ORDER BY position ASC",
                    )?;
                    let rows = stmt.query_map([], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, i64>(2)?,
                        ))
                    })?;
                    for row in rows {
                        let (_legacy_playlist_id, legacy_track_id, _position) = row?;
                        if let Some(track_id) =
                            library::map_legacy_track_id(conn, &legacy_track_id)?
                        {
                            let first_id = conn
                                .query_row(
                                    "SELECT id FROM playlists ORDER BY id ASC LIMIT 1",
                                    [],
                                    |row| row.get::<_, i64>(0),
                                )
                                .optional()?;
                            if let Some(playlist_id) = first_id {
                                playlists::add_track_to_playlist(conn, playlist_id, track_id)?;
                            }
                        }
                    }
                }
                "player_queue" => {
                    let mut stmt = legacy
                        .prepare("SELECT track_id FROM player_queue ORDER BY position ASC")?;
                    let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
                    let mut track_ids = Vec::new();
                    for row in rows {
                        if let Some(track_id) = library::map_legacy_track_id(conn, &row?)? {
                            track_ids.push(track_id);
                        }
                    }
                    queue::replace_queue(conn, &track_ids)?;
                }
                "player_state" => {
                    let mut stmt = legacy.prepare(
                        "SELECT current_track_id, current_queue_index, position_ms, volume, shuffle, repeat_mode, status FROM player_state WHERE id = 1",
                    )?;
                    if let Some((
                        legacy_track_id,
                        queue_index,
                        position_ms,
                        volume,
                        shuffle,
                        repeat_mode,
                        status,
                    )) = stmt
                        .query_row([], |row| {
                            Ok((
                                row.get::<_, Option<String>>(0)?,
                                row.get::<_, i64>(1)?,
                                row.get::<_, i64>(2)?,
                                row.get::<_, f64>(3)?,
                                row.get::<_, bool>(4)?,
                                row.get::<_, String>(5)?,
                                row.get::<_, String>(6)?,
                            ))
                        })
                        .optional()?
                    {
                        let mut playback_state = state::load_playback_state(conn)?;
                        playback_state.current_track_id = legacy_track_id
                            .and_then(|id| library::map_legacy_track_id(conn, &id).ok().flatten());
                        playback_state.queue_index = queue_index;
                        playback_state.position_seconds = position_ms as f64 / 1000.0;
                        playback_state.volume = volume;
                        playback_state.shuffle = shuffle;
                        playback_state.repeat_mode = repeat_mode;
                        playback_state.status = status;
                        state::save_playback_state(conn, &playback_state)?;
                    }
                }
                _ => {}
            }
        }

        // Run extended legacy imports for richer data tables
        let _ = scores::import_scores_from_legacy(conn, &legacy);
        let _ = taste::import_taste_from_legacy(conn, &legacy);
        let _ = acquisition::import_queue_from_legacy(conn, &legacy);
        let _ = acquisition::import_spotify_library_as_queue(conn, &legacy);
        let _ = enrichment::import_enrich_cache_from_legacy(conn, &legacy);

        // Import playback_history — join legacy filepath→new track id, take last 10k rows
        if legacy
            .query_row(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='playback_history'",
                [],
                |_| Ok(1_i64),
            )
            .optional()
            .unwrap_or(None)
            .is_some()
        {
            let stmt = legacy.prepare(
                "SELECT ph.track_id, ph.played_at, ph.context, ph.completion_rate, ph.skipped
                 FROM playback_history ph
                 ORDER BY ph.played_at DESC
                 LIMIT 10000",
            );
            if let Ok(mut stmt) = stmt {
                let rows: Vec<_> = stmt
                    .query_map([], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                            row.get::<_, Option<f64>>(3)?.unwrap_or(1.0),
                            row.get::<_, Option<bool>>(4)?.unwrap_or(false),
                        ))
                    })
                    .unwrap_or_else(|_| unreachable!())
                    .filter_map(Result::ok)
                    .collect();
                for (legacy_id, played_at, context, completion_rate, skipped) in rows {
                    if let Some(track_id) = library::map_legacy_track_id(conn, &legacy_id)
                        .ok()
                        .flatten()
                    {
                        let _ = conn.execute(
                            "INSERT OR IGNORE INTO playback_history
                             (track_id, played_at, context, completion_rate, skipped)
                             VALUES (?1, ?2, ?3, ?4, ?5)",
                            params![track_id, played_at, context, completion_rate, skipped],
                        );
                    }
                }
            }
        }

        // Import vibe_profiles as [Vibe] playlists
        if legacy
            .query_row(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vibe_profiles'",
                [],
                |_| Ok(1_i64),
            )
            .optional()
            .unwrap_or(None)
            .is_some()
        {
            let vibe_rows: Vec<(String, String, String)> = legacy
                .prepare("SELECT vibe_id, name, description FROM vibe_profiles")
                .ok()
                .map(|mut s| {
                    s.query_map([], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                        ))
                    })
                    .unwrap()
                    .filter_map(Result::ok)
                    .collect()
                })
                .unwrap_or_default();

            for (vibe_id, name, _desc) in vibe_rows {
                let playlist_name = format!("[Vibe] {name}");
                if let Ok(playlist_id) = playlists::ensure_playlist(conn, &playlist_name, "") {
                    // pull vibe tracks
                    if let Ok(mut vstmt) = legacy.prepare(
                        "SELECT vt.track_id FROM vibe_tracks vt WHERE vt.vibe_id = ?1 ORDER BY vt.position ASC",
                    ) {
                        let track_ids: Vec<String> = vstmt
                            .query_map(params![vibe_id], |row| row.get::<_, String>(0))
                            .unwrap()
                            .filter_map(Result::ok)
                            .collect();
                        for legacy_tid in track_ids {
                            if let Some(track_id) = library::map_legacy_track_id(conn, &legacy_tid).ok().flatten() {
                                let _ = playlists::add_track_to_playlist(conn, playlist_id, track_id);
                            }
                        }
                    }
                }
            }
        }

        // Import spotify_history latest 1000 as playback events
        if legacy
            .query_row(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='spotify_history'",
                [],
                |_| Ok(1_i64),
            )
            .optional()
            .unwrap_or(None)
            .is_some()
        {
            let stmt = legacy.prepare(
                "SELECT sh.track_id, sh.played_at FROM spotify_history sh ORDER BY sh.played_at DESC LIMIT 1000",
            );
            if let Ok(mut stmt) = stmt {
                let rows: Vec<_> = stmt
                    .query_map([], |row| {
                        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                    })
                    .unwrap()
                    .filter_map(Result::ok)
                    .collect();
                for (legacy_id, played_at) in rows {
                    if let Some(track_id) = library::map_legacy_track_id(conn, &legacy_id)
                        .ok()
                        .flatten()
                    {
                        let _ = conn.execute(
                            "INSERT OR IGNORE INTO playback_history
                             (track_id, played_at, context, completion_rate, skipped)
                             VALUES (?1, ?2, 'spotify_history', 1.0, 0)",
                            params![track_id, played_at],
                        );
                    }
                }
            }
        }

        Ok(imported_tracks)
    }

    pub fn get_native_capabilities(&self) -> NativeCapabilities {
        native::capabilities()
    }

    pub fn get_track_scores(&self, track_id: i64) -> LyraResult<Option<TrackScores>> {
        let conn = self.conn()?;
        scores::get_track_scores(&conn, track_id)
    }

    pub fn get_taste_profile(&self) -> LyraResult<TasteProfile> {
        let conn = self.conn()?;
        taste::get_taste_profile(&conn)
    }

    /// Returns up to `limit` tracks recommended by the oracle based on the current taste profile.
    pub fn get_recommendations(&self, limit: usize) -> LyraResult<Vec<RecommendationResult>> {
        let conn = self.conn()?;
        let taste = taste::get_taste_profile(&conn)?;
        let broker = oracle::RecommendationBroker::new(&conn);
        let scored = broker.recommend_scored(&taste, limit);
        let mut results = Vec::with_capacity(scored.len());
        for (track_id, score) in scored {
            if let Some(track) = library::get_track_by_id(&conn, track_id)? {
                results.push(RecommendationResult { track, score });
            }
        }
        Ok(results)
    }

    /// Returns a human-readable explanation for why a track matches the current taste profile.
    pub fn explain_recommendation(&self, track_id: i64) -> LyraResult<ExplainPayload> {
        let conn = self.conn()?;
        let taste = taste::get_taste_profile(&conn)?;
        Ok(oracle::explain_track(&conn, track_id, &taste))
    }

    pub fn get_acquisition_queue(
        &self,
        status_filter: Option<String>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::list_acquisition_queue(&conn, status_filter.as_deref())
    }

    pub fn add_to_acquisition_queue(
        &self,
        artist: String,
        title: String,
        album: Option<String>,
        source: Option<String>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::add_acquisition_item(
            &conn,
            &artist,
            &title,
            album.as_deref(),
            source.as_deref(),
            0.5,
        )?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    pub fn update_acquisition_item(
        &self,
        id: i64,
        status: String,
        error: Option<String>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::update_acquisition_status(&conn, id, &status, error.as_deref())?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    /// Process the next pending acquisition queue item.
    /// Returns true if an item was processed, false if queue was empty.
    pub fn process_acquisition_queue(&self) -> LyraResult<bool> {
        acquisition_dispatcher::process_next_queue_item(&self.paths)
    }

    /// Start the background acquisition worker.
    pub fn start_acquisition_worker(&self) -> LyraResult<bool> {
        Ok(acquisition_worker::start_worker(self.paths.clone()))
    }

    /// Stop the background acquisition worker.
    pub fn stop_acquisition_worker(&self) -> LyraResult<()> {
        acquisition_worker::stop_worker();
        Ok(())
    }

    /// Check if the acquisition worker is running.
    pub fn acquisition_worker_status(&self) -> LyraResult<bool> {
        Ok(acquisition_worker::is_running())
    }

    /// Run system diagnostics and return health report.
    pub fn run_diagnostics(&self) -> LyraResult<diagnostics::DiagnosticsReport> {
        diagnostics::run_diagnostics(&self.paths)
    }

    pub fn list_playback_history(&self, limit: Option<i64>) -> LyraResult<Vec<PlaybackEvent>> {
        let conn = self.conn()?;
        let limit = limit.unwrap_or(100).min(1000);
        let mut stmt = conn.prepare(
            "SELECT id, track_id, ts, context, completion_rate, skipped
             FROM playback_history ORDER BY ts DESC LIMIT ?1",
        )?;
        let rows = stmt.query_map(params![limit], |row| {
            Ok(PlaybackEvent {
                id: row.get(0)?,
                track_id: row.get(1)?,
                ts: row.get(2)?,
                context: row.get(3)?,
                completion_rate: row.get(4)?,
                skipped: row.get(5)?,
            })
        })?;
        Ok(rows.filter_map(Result::ok).collect())
    }

    pub fn list_recent_plays(&self, limit: Option<i64>) -> LyraResult<Vec<commands::RecentPlayRecord>> {
        let conn = self.conn()?;
        let limit = limit.unwrap_or(20).min(200);
        let mut stmt = conn.prepare(
            "
            SELECT ph.id, ph.track_id,
                   COALESCE(ar.name, ''), COALESCE(t.title, ''),
                   ph.ts, ph.completion_rate, ph.skipped
            FROM playback_history ph
            LEFT JOIN tracks t ON t.id = ph.track_id
            LEFT JOIN artists ar ON ar.id = t.artist_id
            ORDER BY ph.ts DESC LIMIT ?1
            ",
        )?;
        let rows = stmt.query_map(params![limit], |row| {
            Ok(commands::RecentPlayRecord {
                id: row.get(0)?,
                track_id: row.get(1)?,
                artist: row.get(2)?,
                title: row.get(3)?,
                ts: row.get(4)?,
                completion_rate: row.get(5)?,
                skipped: row.get::<_, i64>(6)? != 0,
            })
        })?;
        Ok(rows.filter_map(Result::ok).collect())
    }

    pub fn record_playback_event(
        &self,
        track_id: i64,
        completion_rate: f64,
        context: Option<String>,
    ) -> LyraResult<()> {
        let conn = self.conn()?;
        let now = Utc::now();
        conn.execute(
            "INSERT INTO playback_history (track_id, ts, context, completion_rate, skipped)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                track_id,
                now.to_rfc3339(),
                context.unwrap_or_else(|| "player".to_string()),
                completion_rate,
                completion_rate < 0.1,
            ],
        )?;
        // Update taste profile based on the completion signal.
        let _ = taste::update_taste_from_completion(&conn, track_id, completion_rate);
        // Scrobble to Last.fm if track was played to completion (>=50%).
        if completion_rate >= 0.5 {
            if let Ok(Some(track)) = library::get_track_by_id(&conn, track_id) {
                let duration_secs = track.duration_seconds as u64;
                let ts_unix = now.timestamp();
                let conn2 = self.conn();
                let artist = track.artist.clone();
                let title = track.title.clone();
                let album = track.album.clone();
                std::thread::spawn(move || {
                    if let Ok(c) = conn2 {
                        scrobble::scrobble(&c, &artist, &title, &album, ts_unix, duration_secs);
                    }
                });
            }
        }
        Ok(())
    }

    pub fn get_track_detail(&self, track_id: i64) -> LyraResult<Option<TrackDetail>> {
        let conn = self.conn()?;
        let Some(track) = library::get_track_by_id(&conn, track_id)? else {
            return Ok(None);
        };
        let scores = scores::get_track_scores(&conn, track_id)?;
        Ok(Some(TrackDetail { track, scores }))
    }

    pub fn enrich_track(&self, track_id: i64) -> LyraResult<Value> {
        let conn = self.conn()?;
        let track =
            library::get_track_by_id(&conn, track_id)?.ok_or(LyraError::NotFound("track"))?;
        let dispatcher = enrichment::EnrichmentDispatcher::new(&conn);
        dispatcher.dispatch(&conn, track_id, &track.artist, &track.title, &track.path)
    }

    /// Force-clear the enrich cache for a track across all providers, then re-dispatch.
    /// Returns the fresh enrichment result.
    pub fn refresh_track_enrichment(&self, track_id: i64) -> LyraResult<Value> {
        let conn = self.conn()?;
        let track =
            library::get_track_by_id(&conn, track_id)?.ok_or(LyraError::NotFound("track"))?;

        // Build the lookup keys used per provider and delete cached entries.
        let normalized_key = format!(
            "{}::{}",
            track.artist.trim().to_ascii_lowercase(),
            track.title.trim().to_ascii_lowercase()
        );
        // Delete all provider cache rows for this track
        conn.execute(
            "DELETE FROM enrich_cache WHERE lookup_key = ?1 OR lookup_key = ?2",
            params![normalized_key, track.path],
        )?;

        let dispatcher = enrichment::EnrichmentDispatcher::new(&conn);
        dispatcher.dispatch(&conn, track_id, &track.artist, &track.title, &track.path)
    }

    /// Enrich up to `limit` tracks that have no successful MusicBrainz cache entry yet.
    /// Sleeps 1.1 s between live HTTP requests to respect the MusicBrainz rate limit.
    /// Safe to call in a background thread.
    pub fn enrich_unenriched_tracks(&self, limit: usize) -> LyraResult<usize> {
        use std::time::Duration;

        let conn = self.conn()?;
        // Tracks with no cached MusicBrainz result whose status is "ok".
        let mut stmt = conn.prepare(
            "SELECT t.id, t.artist, t.title, t.file_path
             FROM tracks t
             WHERE NOT EXISTS (
                 SELECT 1 FROM enrich_cache ec
                 WHERE ec.provider = 'musicbrainz'
                   AND ec.lookup_key = lower(trim(t.artist)) || '::' || lower(trim(t.title))
                   AND json_extract(ec.payload_json, '$.status') = 'ok'
             )
             ORDER BY t.id
             LIMIT ?1",
        )?;
        let rows: Vec<(i64, String, String, String)> = stmt
            .query_map(params![limit as i64], |row| {
                Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get::<_, Option<String>>(3)?.unwrap_or_default()))
            })?
            .filter_map(|r| r.ok())
            .collect();

        // Background pass: only MusicBrainz + AcoustID so no credential DB reads are needed
        // and the rate-limit sleep below is sufficient for both providers.
        let dispatcher = enrichment::EnrichmentDispatcher::background();
        let mut dispatched = 0_usize;
        for (track_id, artist, title, path) in rows {
            // Check if already cached (dispatcher is cache-first, but we want to know if we
            // actually made an HTTP call to apply the rate-limit sleep only when needed).
            let cached_before = enrichment::get_enrich_cache(&conn, "musicbrainz",
                &format!("{}::{}", artist.trim().to_ascii_lowercase(), title.trim().to_ascii_lowercase()))?
                .is_some();

            let _ = dispatcher.dispatch(&conn, track_id, &artist, &title, &path);
            dispatched += 1;

            if !cached_before {
                // Live HTTP request was made — respect MusicBrainz 1 req/s policy.
                std::thread::sleep(Duration::from_millis(1100));
            }
        }
        Ok(dispatched)
    }
}
