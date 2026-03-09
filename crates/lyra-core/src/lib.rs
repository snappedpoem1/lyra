pub mod acquisition;
pub mod acquisition_dispatcher;
pub mod acquisition_worker;
pub mod commands;
pub mod composer_diagnostics;
pub mod composer_history;
pub mod config;
pub mod db;
pub mod diagnostics;
pub mod enrichment;
pub mod errors;
pub mod intelligence;
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
pub mod taste_memory;

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use chrono::Utc;
use commands::{
    AcquisitionPreflight, AcquisitionPreflightCheck, AcquisitionQueueItem, ArtistConnection,
    ArtistProfile, AudioOutputDevice, BootstrapPayload, ComposedPlaylistDraft, ComposerResponse,
    DuplicateCluster, ExplainPayload, LegacyImportReport, LibraryOverview, LibraryRootRecord,
    NativeCapabilities, PlaybackEvent, PlaybackState, PlaylistDetail, PlaylistSummary,
    ProviderConfigRecord, ProviderHealth, ProviderValidationResult, QueueItemRecord,
    RecommendationResult, ScanJobRecord, SettingsPayload, SteerPayload, TasteMemorySnapshot,
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

struct ValidationAssessment {
    artist: String,
    title: String,
    album: Option<String>,
    confidence: f64,
    summary: String,
    detail: Option<String>,
    duplicate_path: Option<String>,
}

impl LyraCore {
    fn workspace_root_from_paths(&self) -> Option<PathBuf> {
        self.paths
            .app_data_dir
            .parent()
            .and_then(Path::parent)
            .map(Path::to_path_buf)
    }

    fn command_available(command: &str) -> bool {
        std::process::Command::new("where")
            .arg(command)
            .output()
            .map(|output| output.status.success())
            .unwrap_or(false)
    }

    fn clean_artist_name(value: &str) -> String {
        let mut cleaned = value.trim().to_string();
        for suffix in [" - Topic", " VEVO", " Official"] {
            if cleaned
                .to_ascii_lowercase()
                .ends_with(&suffix.to_ascii_lowercase())
            {
                cleaned.truncate(cleaned.len().saturating_sub(suffix.len()));
                cleaned = cleaned.trim().to_string();
            }
        }
        cleaned
    }

    fn clean_track_title(value: &str) -> String {
        value
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .trim()
            .to_string()
    }

    fn validation_confidence(
        conn: &rusqlite::Connection,
        artist: &str,
        title: &str,
        album: Option<&str>,
    ) -> LyraResult<f64> {
        let known_artist: i64 = conn.query_row(
            "SELECT COUNT(*)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
            params![artist],
            |row| row.get(0),
        )?;
        let exact_track: i64 = conn.query_row(
            "SELECT COUNT(*)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
               AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))",
            params![artist, title],
            |row| row.get(0),
        )?;
        let mut confidence: f64 = 0.42;
        if known_artist > 0 {
            confidence += 0.26;
        }
        if album.is_some() {
            confidence += 0.08;
        }
        if exact_track > 0 {
            confidence += 0.12;
        }
        Ok(confidence.clamp(0.0, 0.97))
    }

    fn validate_acquisition_request(
        conn: &rusqlite::Connection,
        artist: &str,
        title: &str,
        album: Option<&str>,
    ) -> LyraResult<ValidationAssessment> {
        let cleaned_artist = Self::clean_artist_name(artist);
        let cleaned_title = Self::clean_track_title(title);
        let cleaned_album = album.map(Self::clean_track_title);
        let combined = format!("{} {}", cleaned_artist, cleaned_title).to_ascii_lowercase();
        let junk_needles = [
            "karaoke",
            "tribute",
            "cover version",
            "made famous",
            "made popular",
            "in the style of",
            "backing track",
            "lyrics video",
            "audio only",
            "nightcore",
            "slowed",
            "sped up",
            "chopped and screwed",
            "ringtone",
            "music box",
            "8-bit",
            "8 bit",
            "instrumental version",
            "a cappella",
            "acapella",
            "lo-fi",
            "lofi",
            "epic version",
        ];
        if junk_needles.iter().any(|needle| combined.contains(needle)) {
            let confidence = Self::validation_confidence(
                conn,
                &cleaned_artist,
                &cleaned_title,
                cleaned_album.as_deref(),
            )?;
            return Ok(ValidationAssessment {
                artist: cleaned_artist,
                title: cleaned_title,
                album: cleaned_album,
                confidence,
                summary: "Rejected by Rust guard: likely junk, cover, or altered-version metadata"
                    .to_string(),
                detail: Some("Queue item matched local junk-pattern checks".to_string()),
                duplicate_path: None,
            });
        }

        let artist_lower = cleaned_artist.to_ascii_lowercase();
        let record_labels = [
            "atlantic records",
            "columbia records",
            "interscope",
            "def jam",
            "universal music",
            "sony music",
            "warner records",
            "vevo",
            "topic",
            "official video",
            "official audio",
            "lyrical lemonade",
            "worldstarhiphop",
            "monstercat",
            "nocopyrightsounds",
        ];
        if record_labels
            .iter()
            .any(|label| artist_lower == *label || artist_lower.contains(label))
            || artist_lower.ends_with("- topic")
            || artist_lower.ends_with("vevo")
            || artist_lower.contains("official channel")
        {
            let confidence = Self::validation_confidence(
                conn,
                &cleaned_artist,
                &cleaned_title,
                cleaned_album.as_deref(),
            )?;
            return Ok(ValidationAssessment {
                artist: cleaned_artist,
                title: cleaned_title,
                album: cleaned_album,
                confidence,
                summary:
                    "Rejected by Rust guard: artist metadata looks like a label or YouTube channel"
                        .to_string(),
                detail: Some("Queue item matched local artist/label guard checks".to_string()),
                duplicate_path: None,
            });
        }

        let duplicate = conn
            .query_row(
                "SELECT t.path
                 FROM tracks t
                 LEFT JOIN artists ar ON ar.id = t.artist_id
                 WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
                   AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))
                 LIMIT 1",
                params![cleaned_artist, cleaned_title],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        let confidence = Self::validation_confidence(
            conn,
            &cleaned_artist,
            &cleaned_title,
            cleaned_album.as_deref(),
        )?;
        let summary = if duplicate.is_some() {
            "Rejected by Rust guard: track already exists in the library".to_string()
        } else if confidence >= 0.75 {
            "Validated by Rust preflight with strong local confidence".to_string()
        } else if confidence >= 0.55 {
            "Validated by Rust preflight with moderate local confidence".to_string()
        } else {
            "Validated by Rust preflight with limited local confidence".to_string()
        };
        Ok(ValidationAssessment {
            artist: cleaned_artist,
            title: cleaned_title,
            album: cleaned_album,
            confidence,
            summary,
            detail: None,
            duplicate_path: duplicate,
        })
    }

    fn resolve_target_root(
        conn: &rusqlite::Connection,
        target_root_id: Option<i64>,
    ) -> LyraResult<(Option<i64>, Option<String>)> {
        let Some(root_id) = target_root_id else {
            return Ok((None, None));
        };
        let root = library::list_library_roots(conn)?
            .into_iter()
            .find(|root| root.id == root_id);
        Ok(match root {
            Some(root) => (Some(root.id), Some(root.path)),
            None => (None, None),
        })
    }

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

    fn legacy_db_path(&self) -> PathBuf {
        std::env::var("LYRA_DB_PATH")
            .ok()
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("lyra_registry.db"))
    }

    fn with_attached_legacy_db<T, F>(&self, callback: F) -> LyraResult<Option<T>>
    where
        F: FnOnce(&rusqlite::Connection, &Path) -> LyraResult<T>,
    {
        let legacy_path = self.legacy_db_path();
        if !legacy_path.exists() {
            return Ok(None);
        }

        let conn = self.conn()?;
        conn.execute(
            "ATTACH DATABASE ?1 AS legacy_spotify",
            params![legacy_path.display().to_string()],
        )?;
        let result = callback(&conn, &legacy_path);
        let detach_result = conn.execute("DETACH DATABASE legacy_spotify", []);

        match (result, detach_result) {
            (Ok(value), Ok(_)) => Ok(Some(value)),
            (Err(error), _) => Err(error),
            (Ok(_), Err(error)) => Err(error.into()),
        }
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
            taste_memory: taste_memory::load_snapshot(&conn)
                .unwrap_or_else(|_| TasteMemorySnapshot::default()),
            acquisition_queue_pending: acquisition::pending_count(&conn),
        })
    }

    pub fn list_tracks(
        &self,
        query: Option<String>,
        sort: Option<String>,
    ) -> LyraResult<Vec<TrackRecord>> {
        let conn = self.conn()?;
        library::list_tracks(&conn, query, sort)
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
                if library::is_supported_audio_file(entry.path())
                    && library::import_track_from_path(&conn, entry.path())?
                {
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
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let next = controller.stop(current.volume);
        state::save_playback_state(&conn, &next)?;
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
        let current = state::load_playback_state(&conn)?;
        let mut controller = self.playback.lock().map_err(|_| LyraError::LockPoisoned)?;
        let mut next = controller.stop(current.volume);
        next.status = "stopped".to_string();
        state::save_playback_state(&conn, &next)?;
        Ok(next)
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
                (
                    0.max(fallback),
                    queue_items
                        .first()
                        .ok_or(LyraError::InvalidInput("queue is empty"))?,
                )
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

    pub fn validate_provider(&self, provider_key: String) -> LyraResult<ProviderValidationResult> {
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
    pub fn keyring_delete(&self, provider_key: String, key_name: String) -> Result<(), String> {
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

    pub fn resolve_duplicate_cluster(
        &self,
        keep_track_id: i64,
        remove_track_ids: Vec<i64>,
    ) -> LyraResult<()> {
        let conn = self.conn()?;
        library::resolve_duplicate_cluster(&conn, keep_track_id, remove_track_ids)
    }

    pub fn get_curation_log(&self) -> LyraResult<Vec<commands::CurationLogEntry>> {
        let conn = self.conn()?;
        library::get_curation_log(&conn)
    }

    pub fn undo_curation(&self, log_id: i64) -> LyraResult<()> {
        let conn = self.conn()?;
        library::undo_curation(&conn, log_id)
    }

    pub fn preview_library_cleanup(&self) -> LyraResult<commands::LibraryCleanupPreview> {
        let conn = self.conn()?;
        library::preview_library_cleanup(&conn)
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

    /// Returns up to `limit` tracks recommended by the broker with multi-lane evidence.
    /// Lanes: local/taste, local/deep_cut, scout/bridge (cross-genre), graph/co_play.
    pub fn get_recommendations(&self, limit: usize) -> LyraResult<Vec<RecommendationResult>> {
        let conn = self.conn()?;
        let taste = taste::get_taste_profile(&conn)?;
        let broker = oracle::RecommendationBroker::new(&conn);
        Ok(broker.recommend_with_evidence(&taste, limit))
    }

    pub fn compose_playlist_draft(
        &self,
        prompt: String,
        track_count: usize,
    ) -> LyraResult<ComposedPlaylistDraft> {
        let conn = self.conn()?;
        let settings = state::load_settings(&conn)?;
        intelligence::compose_playlist_draft(&conn, &settings, &prompt, track_count)
    }

    pub fn compose_with_lyra(
        &self,
        prompt: String,
        track_count: usize,
        steer: Option<SteerPayload>,
    ) -> LyraResult<ComposerResponse> {
        let conn = self.conn()?;
        let settings = state::load_settings(&conn)?;
        match intelligence::compose_composer_response(
            &conn,
            &settings,
            &prompt,
            track_count,
            steer.as_ref(),
        ) {
            Ok(mut response) => {
                response.taste_memory = taste_memory::capture_compose_memory(
                    &conn,
                    &prompt,
                    steer.as_ref(),
                    &response,
                )?;
                let run_id = composer_history::save_run(&conn, &prompt, &response).ok();
                let action_label = format!("{:?}", response.action).to_ascii_lowercase();
                let payload = serde_json::json!({
                    "runId": run_id,
                    "activeRole": response.active_role,
                    "fallbackActive": response.framing.fallback.active,
                    "providerKind": response.provider_status.provider_kind,
                    "memoryHint": response.framing.memory_hint,
                    "routeComparison": response.framing.route_comparison.as_ref().map(|comparison| comparison.headline.clone()),
                });
                composer_diagnostics::record_event(
                    &conn,
                    composer_diagnostics::ComposerDiagnosticWrite {
                        level: "info".to_string(),
                        event_type: "compose_success".to_string(),
                        prompt: prompt.clone(),
                        action: Some(action_label),
                        provider: response.provider_status.selected_provider.clone(),
                        mode: response.provider_status.mode.clone(),
                        message: "Lyra composed a response successfully.".to_string(),
                        payload: Some(payload),
                    },
                )?;
                Ok(response)
            }
            Err(error) => {
                let _ = composer_diagnostics::record_event(
                    &conn,
                    composer_diagnostics::ComposerDiagnosticWrite {
                        level: "error".to_string(),
                        event_type: "compose_failure".to_string(),
                        prompt,
                        action: None,
                        provider: "unknown".to_string(),
                        mode: "failed".to_string(),
                        message: error.to_string(),
                        payload: Some(serde_json::json!({
                            "trackCount": track_count,
                            "steer": steer,
                        })),
                    },
                );
                Err(error)
            }
        }
    }

    pub fn save_composed_playlist(
        &self,
        name: String,
        draft: ComposedPlaylistDraft,
    ) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        let playlist_id = intelligence::save_composed_playlist(&conn, &name, &draft)?;
        self.get_playlist_detail(playlist_id)
    }

    pub fn record_route_feedback(
        &self,
        payload: commands::RouteFeedbackPayload,
    ) -> LyraResult<commands::TasteMemorySnapshot> {
        let conn = self.conn()?;
        taste_memory::record_route_feedback(&conn, &payload)
    }

    /// Generate an act-based playlist from a user intent.
    pub fn generate_act_playlist(
        &self,
        intent: String,
        track_count: usize,
    ) -> LyraResult<commands::GeneratedPlaylist> {
        let conn = self.conn()?;
        playlists::generate_act_playlist(&intent, track_count, &conn)
    }

    /// Save a generated playlist and store per-track reasons.
    pub fn save_generated_playlist(
        &self,
        name: String,
        playlist: commands::GeneratedPlaylist,
    ) -> LyraResult<PlaylistDetail> {
        let conn = self.conn()?;
        let playlist_id = playlists::save_generated_playlist(&name, &playlist, &conn)?;
        self.get_playlist_detail(playlist_id)
    }

    /// Return persisted reason payloads for a playlist.
    pub fn get_playlist_track_reasons(
        &self,
        playlist_id: i64,
    ) -> LyraResult<Vec<commands::PlaylistTrackReasonRecord>> {
        let conn = self.conn()?;
        playlists::get_playlist_track_reasons(&conn, playlist_id)
    }

    pub fn get_composer_diagnostics(
        &self,
        limit: usize,
    ) -> LyraResult<Vec<commands::ComposerDiagnosticEntry>> {
        let conn = self.conn()?;
        composer_diagnostics::recent(&conn, limit)
    }

    pub fn get_recent_composer_runs(
        &self,
        limit: usize,
    ) -> LyraResult<Vec<commands::ComposerRunRecord>> {
        let conn = self.conn()?;
        composer_history::recent(&conn, limit)
    }

    pub fn get_composer_run(&self, run_id: i64) -> LyraResult<commands::ComposerRunDetail> {
        let conn = self.conn()?;
        composer_history::detail(&conn, run_id)
    }

    pub fn get_spotify_gap_summary(&self, limit: usize) -> LyraResult<commands::SpotifyGapSummary> {
        let top_limit = i64::try_from(limit.max(1)).unwrap_or(12);
        let candidate_limit = i64::try_from(limit.max(3) * 2).unwrap_or(24);
        let summary = self.with_attached_legacy_db(|conn, legacy_path| {
            let history_exists = conn
                .query_row(
                    "SELECT 1 FROM legacy_spotify.sqlite_master WHERE type = 'table' AND name = 'spotify_history'",
                    [],
                    |_| Ok(1_i64),
                )
                .optional()?
                .is_some();
            let library_exists = conn
                .query_row(
                    "SELECT 1 FROM legacy_spotify.sqlite_master WHERE type = 'table' AND name = 'spotify_library'",
                    [],
                    |_| Ok(1_i64),
                )
                .optional()?
                .is_some();
            let features_exists = conn
                .query_row(
                    "SELECT 1 FROM legacy_spotify.sqlite_master WHERE type = 'table' AND name = 'spotify_features'",
                    [],
                    |_| Ok(1_i64),
                )
                .optional()?
                .is_some();

            if !history_exists && !library_exists {
                return Ok(commands::SpotifyGapSummary {
                    available: false,
                    db_path: Some(legacy_path.display().to_string()),
                    history_count: 0,
                    library_count: 0,
                    features_count: 0,
                    owned_overlap_count: 0,
                    queued_overlap_count: 0,
                    recoverable_missing_count: 0,
                    top_artists: Vec::new(),
                    missing_candidates: Vec::new(),
                    summary_lines: vec![
                        "Cassette found a legacy database path, but no Spotify history or library tables are present yet.".to_string(),
                    ],
                });
            }

            let history_count = if history_exists {
                conn.query_row("SELECT COUNT(*) FROM legacy_spotify.spotify_history", [], |row| row.get(0))?
            } else {
                0
            };
            let library_count = if library_exists {
                conn.query_row("SELECT COUNT(*) FROM legacy_spotify.spotify_library", [], |row| row.get(0))?
            } else {
                0
            };
            let features_count = if features_exists {
                conn.query_row("SELECT COUNT(*) FROM legacy_spotify.spotify_features", [], |row| row.get(0))?
            } else {
                0
            };

            let owned_overlap_count = if library_exists {
                conn.query_row(
                    "SELECT COUNT(*)
                     FROM legacy_spotify.spotify_library sl
                     WHERE EXISTS (
                        SELECT 1
                        FROM tracks t
                        LEFT JOIN artists ar ON ar.id = t.artist_id
                        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                     )",
                    [],
                    |row| row.get(0),
                )?
            } else {
                0
            };

            let queued_overlap_count = if library_exists {
                conn.query_row(
                    "SELECT COUNT(*)
                     FROM legacy_spotify.spotify_library sl
                     WHERE NOT EXISTS (
                        SELECT 1
                        FROM tracks t
                        LEFT JOIN artists ar ON ar.id = t.artist_id
                        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                     )
                     AND EXISTS (
                        SELECT 1
                        FROM acquisition_queue aq
                        WHERE lower(trim(COALESCE(aq.artist, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(aq.title, ''))) = lower(trim(sl.title))
                          AND aq.status NOT IN ('completed', 'cancelled')
                     )",
                    [],
                    |row| row.get(0),
                )?
            } else {
                0
            };

            let recoverable_missing_count = if library_exists {
                conn.query_row(
                    "SELECT COUNT(*)
                     FROM legacy_spotify.spotify_library sl
                     WHERE NOT EXISTS (
                        SELECT 1
                        FROM tracks t
                        LEFT JOIN artists ar ON ar.id = t.artist_id
                        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                     )
                     AND NOT EXISTS (
                        SELECT 1
                        FROM acquisition_queue aq
                        WHERE lower(trim(COALESCE(aq.artist, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(aq.title, ''))) = lower(trim(sl.title))
                          AND aq.status NOT IN ('completed', 'cancelled')
                     )",
                    [],
                    |row| row.get(0),
                )?
            } else {
                0
            };

            let top_artists = if history_exists {
                let mut stmt = conn.prepare(
                    "WITH artist_plays AS (
                        SELECT
                            trim(artist) AS artist,
                            COUNT(*) AS play_count,
                            SUM(COALESCE(ms_played, 0)) AS total_ms_played,
                            MAX(played_at) AS last_played_at
                        FROM legacy_spotify.spotify_history
                        WHERE artist IS NOT NULL AND trim(artist) != ''
                        GROUP BY lower(trim(artist))
                    )
                    SELECT
                        ap.artist,
                        ap.play_count,
                        ap.total_ms_played,
                        (
                            SELECT COUNT(*)
                            FROM tracks t
                            LEFT JOIN artists ar ON ar.id = t.artist_id
                            WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(ap.artist))
                        ) AS owned_track_count,
                        (
                            SELECT COUNT(*)
                            FROM legacy_spotify.spotify_library sl
                            WHERE lower(trim(sl.artist)) = lower(trim(ap.artist))
                              AND NOT EXISTS (
                                SELECT 1
                                FROM tracks t
                                LEFT JOIN artists ar ON ar.id = t.artist_id
                                WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                                  AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                              )
                        ) AS missing_track_count,
                        ap.last_played_at
                     FROM artist_plays ap
                     ORDER BY ap.play_count DESC, ap.total_ms_played DESC
                     LIMIT ?1",
                )?;
                let rows = stmt.query_map(params![top_limit], |row| {
                    Ok(commands::SpotifyTopArtist {
                        artist: row.get(0)?,
                        play_count: row.get(1)?,
                        total_ms_played: row.get(2)?,
                        owned_track_count: row.get(3)?,
                        missing_track_count: row.get(4)?,
                        last_played_at: row.get(5)?,
                    })
                })?;
                rows.filter_map(Result::ok).collect()
            } else {
                Vec::new()
            };

            let missing_candidates = if library_exists {
                let mut stmt = conn.prepare(
                    "WITH history_counts AS (
                        SELECT
                            lower(trim(artist)) AS artist_key,
                            lower(trim(track)) AS title_key,
                            COUNT(*) AS play_count,
                            MAX(played_at) AS last_played_at
                        FROM legacy_spotify.spotify_history
                        WHERE artist IS NOT NULL AND trim(artist) != ''
                          AND track IS NOT NULL AND trim(track) != ''
                        GROUP BY artist_key, title_key
                    )
                    SELECT
                        sl.artist,
                        sl.title,
                        sl.album,
                        sl.spotify_uri,
                        COALESCE(sl.source, 'liked') AS source,
                        COALESCE(h.play_count, 0) AS play_count,
                        h.last_played_at,
                        EXISTS (
                            SELECT 1
                            FROM acquisition_queue aq
                            WHERE lower(trim(COALESCE(aq.artist, ''))) = lower(trim(sl.artist))
                              AND lower(trim(COALESCE(aq.title, ''))) = lower(trim(sl.title))
                              AND aq.status NOT IN ('completed', 'cancelled')
                        ) AS already_queued
                    FROM legacy_spotify.spotify_library sl
                    LEFT JOIN history_counts h
                        ON h.artist_key = lower(trim(sl.artist))
                       AND h.title_key = lower(trim(sl.title))
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM tracks t
                        LEFT JOIN artists ar ON ar.id = t.artist_id
                        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                          AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                    )
                    ORDER BY COALESCE(h.play_count, 0) DESC,
                             h.last_played_at DESC,
                             sl.added_at DESC
                    LIMIT ?1",
                )?;
                let rows = stmt.query_map(params![candidate_limit], |row| {
                    Ok(commands::SpotifyMissingCandidate {
                        artist: row.get(0)?,
                        title: row.get(1)?,
                        album: row.get(2)?,
                        spotify_uri: row.get(3)?,
                        source: row.get(4)?,
                        play_count: row.get(5)?,
                        last_played_at: row.get(6)?,
                        already_queued: row.get::<_, bool>(7)?,
                    })
                })?;
                rows.filter_map(Result::ok).collect()
            } else {
                Vec::new()
            };

            let summary_lines = if !library_exists && history_exists {
                vec![
                    format!("Spotify history is present with {history_count} plays, but no liked-library export was found to compare against ownership."),
                    "Lyra can treat that history as taste pressure, but missing-world recovery is still underfed until the library export is present.".to_string(),
                ]
            } else if library_exists {
                vec![
                    format!(
                        "Cassette found {library_count} Spotify library entries; {recoverable_missing_count} are still missing from your owned world and not yet queued."
                    ),
                    format!(
                        "{owned_overlap_count} already overlap with the local library, and {queued_overlap_count} more are already in the acquisition lane."
                    ),
                ]
            } else {
                vec!["Spotify evidence is not available yet.".to_string()]
            };

            Ok(commands::SpotifyGapSummary {
                available: history_exists || library_exists,
                db_path: Some(legacy_path.display().to_string()),
                history_count,
                library_count,
                features_count,
                owned_overlap_count,
                queued_overlap_count,
                recoverable_missing_count,
                top_artists,
                missing_candidates,
                summary_lines,
            })
        })?;

        Ok(summary.unwrap_or(commands::SpotifyGapSummary {
            available: false,
            db_path: Some(self.legacy_db_path().display().to_string()),
            history_count: 0,
            library_count: 0,
            features_count: 0,
            owned_overlap_count: 0,
            queued_overlap_count: 0,
            recoverable_missing_count: 0,
            top_artists: Vec::new(),
            missing_candidates: Vec::new(),
            summary_lines: vec![
                "Cassette could not find a Spotify export database yet. Set LYRA_DB_PATH or keep lyra_registry.db in the repo root to surface that lane.".to_string(),
            ],
        }))
    }

    /// Get related artists for a given artist name.
    pub fn get_related_artists(
        &self,
        artist_name: String,
        limit: usize,
    ) -> LyraResult<Vec<commands::RelatedArtist>> {
        let conn = self.conn()?;
        oracle::record_discovery_interaction(&artist_name, "view_related", &conn);
        Ok(oracle::get_related_artists(&artist_name, limit, &conn))
    }

    /// Queue tracks from artists similar to the given artist.
    pub fn play_similar_to_artist(
        &self,
        artist_name: String,
        limit: usize,
    ) -> LyraResult<Vec<QueueItemRecord>> {
        let conn = self.conn()?;
        oracle::record_discovery_interaction(&artist_name, "play_similar", &conn);
        let track_ids = oracle::play_similar_to_artist(&artist_name, limit, &conn);
        if !track_ids.is_empty() {
            queue::enqueue_tracks(&conn, &track_ids)?;
        }
        self.get_queue()
    }

    /// Return the last 10 discovery interactions.
    pub fn get_discovery_session(&self) -> LyraResult<commands::DiscoverySession> {
        let conn = self.conn()?;
        Ok(oracle::get_discovery_session(&conn))
    }

    /// Build dimension-affinity edges between artists from local track_scores centroids.
    /// Returns the count of new artist pairs inserted into the connections table.
    pub fn build_artist_graph(&self) -> LyraResult<usize> {
        let conn = self.conn()?;
        Ok(oracle::build_dimension_affinity(&conn))
    }

    /// Return graph statistics: total artists, total connections, top connected artists.
    pub fn get_graph_stats(&self) -> LyraResult<commands::GraphStats> {
        let conn = self.conn()?;
        let total_artists: i64 = conn
            .query_row("SELECT COUNT(DISTINCT source) FROM connections", [], |r| {
                r.get(0)
            })
            .unwrap_or(0);
        let total_connections: i64 = conn
            .query_row("SELECT COUNT(*) FROM connections", [], |r| r.get(0))
            .unwrap_or(0);
        let top_connected: Vec<commands::GraphNode> = {
            let mut stmt = conn
                .prepare(
                    "SELECT source, COUNT(*) AS cnt FROM connections
                     GROUP BY source ORDER BY cnt DESC LIMIT 5",
                )
                .map_err(crate::LyraError::Db)?;
            stmt.query_map([], |row| {
                Ok(commands::GraphNode {
                    artist: row.get(0)?,
                    degree: row.get::<_, i64>(1)? as usize,
                })
            })
            .map(|rows| rows.filter_map(Result::ok).collect())
            .unwrap_or_default()
        };
        Ok(commands::GraphStats {
            total_artists: total_artists as usize,
            total_connections: total_connections as usize,
            top_connected,
        })
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
        target_root_id: Option<i64>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        let validation =
            Self::validate_acquisition_request(&conn, &artist, &title, album.as_deref())?;
        let (target_root_id, target_root_path) = Self::resolve_target_root(&conn, target_root_id)?;
        let priority = acquisition::compute_initial_priority(
            &conn,
            &validation.artist,
            &validation.title,
            validation.album.as_deref(),
            source.as_deref(),
        )?;
        let item = acquisition::add_acquisition_item(
            &conn,
            &validation.artist,
            &validation.title,
            validation.album.as_deref(),
            source.as_deref(),
            priority,
            Some(validation.confidence),
            Some(&validation.summary),
            target_root_id,
            target_root_path.as_deref(),
        )?;
        if let Some(path) = validation.duplicate_path.as_deref() {
            acquisition::mark_failed(
                &conn,
                item.id,
                "validating",
                "Track already exists in the library",
                Some(path),
            )?;
            acquisition::apply_validation_metadata(
                &conn,
                item.id,
                Some(validation.confidence),
                Some(&validation.summary),
            )?;
        } else if validation.summary.starts_with("Rejected by Rust guard:") {
            acquisition::mark_failed(
                &conn,
                item.id,
                "validating",
                &validation.summary,
                validation.detail.as_deref().or(Some(
                    "Queue item was blocked before the provider waterfall started",
                )),
            )?;
            acquisition::apply_validation_metadata(
                &conn,
                item.id,
                Some(validation.confidence),
                Some(&validation.summary),
            )?;
        }
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

    pub fn clear_completed_acquisition(&self) -> LyraResult<i64> {
        let conn = self.conn()?;
        acquisition::clear_completed(&conn)
    }

    pub fn cancel_acquisition_item(
        &self,
        id: i64,
        detail: Option<String>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::request_cancel(&conn, id, detail.as_deref())?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    pub fn retry_failed_acquisition(&self) -> LyraResult<i64> {
        let conn = self.conn()?;
        acquisition::retry_failed(&conn)
    }

    /// Seed the acquisition queue from the legacy Spotify liked library.
    ///
    /// Opens `lyra_registry.db` (or the path from `LYRA_DB_PATH` env var) and
    /// imports any `spotify_library` liked tracks that are not yet owned locally
    /// and not already in the acquisition queue.
    ///
    /// Returns the number of new items added.
    pub fn seed_acquisition_from_spotify_library(&self) -> LyraResult<usize> {
        let conn = self.conn()?;
        let legacy_path = self.legacy_db_path();
        if !legacy_path.exists() {
            return Ok(0);
        }
        let legacy = rusqlite::Connection::open(&legacy_path)?;
        acquisition::import_spotify_library_as_queue(&conn, &legacy)
    }

    /// Bulk-add multiple tracks to the acquisition queue from a text list.
    ///
    /// Each entry is `(artist, title, album_opt, source)`. Duplicate detection
    /// and priority scoring run per-track via the normal acquisition path.
    ///
    /// Returns the list of newly added queue items.
    pub fn bulk_add_to_acquisition_queue(
        &self,
        entries: Vec<(String, String, Option<String>)>,
        source: String,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        let mut added: Vec<AcquisitionQueueItem> = Vec::new();
        for (artist, title, album) in entries {
            if artist.trim().is_empty() || title.trim().is_empty() {
                continue;
            }
            let validation = Self::validate_acquisition_request(
                &conn,
                artist.trim(),
                title.trim(),
                album.as_deref(),
            )?;
            let (target_root_id, target_root_path) = Self::resolve_target_root(&conn, None)?;
            let priority = acquisition::compute_initial_priority(
                &conn,
                &validation.artist,
                &validation.title,
                validation.album.as_deref(),
                Some(source.as_str()),
            )?;
            let item = acquisition::add_acquisition_item(
                &conn,
                &validation.artist,
                &validation.title,
                validation.album.as_deref(),
                Some(source.as_str()),
                priority,
                Some(validation.confidence),
                Some(&validation.summary),
                target_root_id,
                target_root_path.as_deref(),
            )?;
            added.push(item);
        }
        Ok(added)
    }

    pub fn set_acquisition_priority(
        &self,
        id: i64,
        priority_score: f64,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::set_priority(&conn, id, priority_score)?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    pub fn move_acquisition_queue_item(
        &self,
        id: i64,
        new_position: i64,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        acquisition::move_queue_item(&conn, id, new_position)?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    pub fn set_acquisition_target_root(
        &self,
        id: i64,
        target_root_id: Option<i64>,
    ) -> LyraResult<Vec<AcquisitionQueueItem>> {
        let conn = self.conn()?;
        let (resolved_id, target_root_path) = Self::resolve_target_root(&conn, target_root_id)?;
        acquisition::set_target_root(&conn, id, resolved_id, target_root_path.as_deref())?;
        acquisition::list_acquisition_queue(&conn, None)
    }

    pub fn acquisition_preflight(&self) -> LyraResult<AcquisitionPreflight> {
        let required_bytes: i64 = 500 * 1024 * 1024;
        let workspace_root = self.workspace_root_from_paths();
        let conn = self.conn()?;
        let provider_configs = providers::list_provider_configs(&conn)?;
        let provider_config = |key: &str, config_key: &str, env_key: &str, default: &str| {
            provider_configs
                .iter()
                .find(|record| record.provider_key == key)
                .and_then(|record| {
                    record
                        .config
                        .get(config_key)
                        .or_else(|| record.config.get(env_key))
                })
                .and_then(Value::as_str)
                .map(str::to_string)
                .or_else(|| std::env::var(env_key).ok())
                .unwrap_or_else(|| default.to_string())
        };
        let python_path = workspace_root
            .as_ref()
            .map(|root| root.join(".venv").join("Scripts").join("python.exe"));
        let python_available = python_path.as_ref().is_some_and(|p| p.exists());
        let waterfall_script = workspace_root
            .as_ref()
            .map(|root| root.join("oracle").join("acquirers").join("waterfall.py"));
        let waterfall_available = waterfall_script.as_ref().is_some_and(|p| p.exists());
        let qobuz_service_url = provider_config(
            "qobuz",
            "qobuz_service_url",
            "QOBUZ_SERVICE_URL",
            "http://localhost:7700",
        );
        let qobuz_service_available = ureq::get(&format!(
            "{}/health",
            qobuz_service_url.trim_end_matches('/')
        ))
        .call()
        .is_ok();
        let slskd_url = provider_config("slskd", "slskd_url", "SLSKD_URL", "http://localhost:5030");
        let slskd_api_base = std::env::var("LYRA_PROTOCOL_NODE_API_BASE")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "/api/v0".to_string());
        let slskd_application_url = format!(
            "{}/{}/application",
            slskd_url.trim_end_matches('/'),
            slskd_api_base.trim_matches('/')
        );
        let slskd_available = match ureq::get(&slskd_application_url).call() {
            Ok(_) => true,
            Err(ureq::Error::Status(code, _)) => matches!(code, 401 | 403),
            Err(_) => false,
        };
        let downloader_tools = [
            ("qobuz-service", qobuz_service_available),
            ("spotdl", Self::command_available("spotdl")),
            ("streamrip", Self::command_available("rip")),
            ("slskd", slskd_available),
        ];
        let native_downloader_available = downloader_tools.iter().any(|(_, ok)| *ok);
        let python_bridge_available =
            python_available && waterfall_available && native_downloader_available;
        let downloader_available = native_downloader_available || python_bridge_available;

        let mut free_bytes: i64 = 0;
        let acquisition_root = std::env::var("LYRA_DATA_ROOT")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var("LOCALAPPDATA")
                    .ok()
                    .filter(|value| !value.trim().is_empty())
                    .map(PathBuf::from)
                    .map(|root| root.join("Lyra").join("dev"))
            })
            .or_else(|| workspace_root.as_ref().map(|root| root.join(".lyra-data")))
            .unwrap_or_else(|| self.paths.app_data_dir.clone());
        let staging_dir = std::env::var("STAGING_FOLDER")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| acquisition_root.join("staging"));
        let downloads_dir = std::env::var("DOWNLOADS_FOLDER")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| acquisition_root.join("downloads"));

        if let Ok(space) = fs2::available_space(&downloads_dir) {
            free_bytes = space as i64;
        }
        let disk_ok = free_bytes >= required_bytes;
        let library_roots = library::list_library_roots(&conn)?;
        let library_root_ok = !library_roots.is_empty()
            && library_roots
                .iter()
                .any(|root| PathBuf::from(&root.path).exists());
        let output_path_ok = create_dir_all_if_missing(&downloads_dir).is_ok()
            && create_dir_all_if_missing(&staging_dir).is_ok()
            && is_path_writable(&downloads_dir)
            && is_path_writable(&staging_dir);

        let mut notes = Vec::new();
        let mut checks = Vec::new();
        if !python_available && native_downloader_available {
            notes.push("Python runtime not found in .venv; Rust will use native acquisition providers where possible.".to_string());
        } else if !python_available {
            notes.push("Python runtime not found in .venv".to_string());
        }
        if !waterfall_available && python_available {
            notes.push("Legacy waterfall bridge not found at oracle/acquirers/waterfall.py; Rust native providers only.".to_string());
        }
        if !downloader_available {
            notes.push("No supported acquisition downloader tool detected on PATH".to_string());
        } else {
            let available_tools = downloader_tools
                .iter()
                .filter_map(|(tool, ok)| ok.then_some(*tool))
                .collect::<Vec<_>>()
                .join(", ");
            notes.push(format!("Detected downloader tools: {available_tools}"));
        }
        if !disk_ok {
            notes.push(format!(
                "Insufficient free space: {} MB available, {} MB required",
                free_bytes / (1024 * 1024),
                required_bytes / (1024 * 1024)
            ));
        }
        if !library_root_ok {
            notes.push(
                "No accessible library root is configured for post-acquisition organization."
                    .to_string(),
            );
        }
        if !output_path_ok {
            notes.push(format!(
                "Acquisition staging/download paths are not writable: {} ; {}",
                downloads_dir.display(),
                staging_dir.display()
            ));
        }

        checks.push(AcquisitionPreflightCheck {
            key: "python_runtime".to_string(),
            label: "Python runtime".to_string(),
            status: if python_available {
                "ok"
            } else if native_downloader_available {
                "warning"
            } else {
                "failed"
            }
            .to_string(),
            detail: python_path
                .as_ref()
                .map(|path| {
                    if path.exists() {
                        path.display().to_string()
                    } else {
                        format!("{} (native providers can still run)", path.display())
                    }
                })
                .unwrap_or_else(|| "Python venv not configured".to_string()),
        });
        checks.push(AcquisitionPreflightCheck {
            key: "provider_readiness".to_string(),
            label: "Provider/tool readiness".to_string(),
            status: if downloader_available {
                "ok"
            } else {
                "warning"
            }
            .to_string(),
            detail: if downloader_available {
                downloader_tools
                    .iter()
                    .filter_map(|(tool, ok)| ok.then_some(*tool))
                    .collect::<Vec<_>>()
                    .join(", ")
            } else {
                "No supported acquisition downloader tool detected on PATH".to_string()
            },
        });
        checks.push(AcquisitionPreflightCheck {
            key: "disk_space".to_string(),
            label: "Disk space".to_string(),
            status: if disk_ok { "ok" } else { "failed" }.to_string(),
            detail: format!(
                "{} MB free in {}",
                free_bytes / (1024 * 1024),
                downloads_dir.display()
            ),
        });
        checks.push(AcquisitionPreflightCheck {
            key: "library_root".to_string(),
            label: "Library root".to_string(),
            status: if library_root_ok { "ok" } else { "failed" }.to_string(),
            detail: if let Some(root) = library_roots.first() {
                root.path.clone()
            } else {
                "Configure at least one writable library root for organize/index completion"
                    .to_string()
            },
        });
        checks.push(AcquisitionPreflightCheck {
            key: "output_paths".to_string(),
            label: "Staging and downloads".to_string(),
            status: if output_path_ok { "ok" } else { "failed" }.to_string(),
            detail: format!(
                "downloads={} | staging={}",
                downloads_dir.display(),
                staging_dir.display()
            ),
        });

        if notes.is_empty() {
            notes.push("Preflight checks passed".to_string());
        }
        Ok(AcquisitionPreflight {
            ready: downloader_available && disk_ok && library_root_ok && output_path_ok,
            python_available,
            downloader_available,
            disk_ok,
            library_root_ok,
            output_path_ok,
            free_bytes,
            required_bytes,
            checks,
            notes,
        })
    }

    /// Process the next pending acquisition queue item.
    /// Returns true if an item was processed, false if queue was empty.
    pub fn process_acquisition_queue(&self) -> LyraResult<bool> {
        acquisition_dispatcher::process_next_queue_item(&self.paths)
    }

    pub fn process_acquisition_queue_with_callback<F>(&self, notify: F) -> LyraResult<bool>
    where
        F: Fn(i64) + Send + Sync + 'static,
    {
        acquisition_dispatcher::process_next_queue_item_with_callback(&self.paths, notify)
    }

    /// Start the background acquisition worker.
    pub fn start_acquisition_worker(&self) -> LyraResult<bool> {
        Ok(acquisition_worker::start_worker(self.paths.clone()))
    }

    pub fn start_acquisition_worker_with_callback<F>(&self, notify: F) -> LyraResult<bool>
    where
        F: Fn(i64) + Send + Sync + 'static,
    {
        Ok(acquisition_worker::start_worker_with_callback(
            self.paths.clone(),
            notify,
        ))
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

    pub fn list_recent_plays(
        &self,
        limit: Option<i64>,
    ) -> LyraResult<Vec<commands::RecentPlayRecord>> {
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

    fn build_track_enrichment_result(
        &self,
        conn: &rusqlite::Connection,
        track: &TrackRecord,
    ) -> LyraResult<commands::TrackEnrichmentResult> {
        use crate::commands::{EnrichmentEntry, TrackEnrichmentResult};

        let normalized_key = format!(
            "{}::{}",
            track.artist.trim().to_ascii_lowercase(),
            track.title.trim().to_ascii_lowercase()
        );
        let lookup_keys = if track.path.trim().is_empty() {
            vec![normalized_key]
        } else {
            vec![normalized_key, track.path.clone()]
        };

        let mut best_by_provider: std::collections::HashMap<String, EnrichmentEntry> =
            std::collections::HashMap::new();

        for lookup_key in lookup_keys {
            let mut stmt = conn.prepare(
                "SELECT provider, payload_json
                 FROM enrich_cache
                 WHERE lookup_key = ?1",
            )?;
            let rows = stmt.query_map(params![lookup_key], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })?;

            for row in rows.filter_map(Result::ok) {
                let (provider, payload_json) = row;
                let Ok(payload) = serde_json::from_str::<Value>(&payload_json) else {
                    continue;
                };

                let status = payload
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
                    .to_string();
                let match_score_raw = payload
                    .get("matchScore")
                    .and_then(Value::as_f64)
                    .or_else(|| payload.get("score").and_then(Value::as_f64));
                let confidence = match match_score_raw {
                    Some(score) if score > 1.0 => (score / 100.0).min(1.0) as f32,
                    Some(score) => score as f32,
                    None if status == "ok" => 1.0,
                    _ => 0.0,
                };
                let note = payload
                    .get("error")
                    .and_then(Value::as_str)
                    .or_else(|| payload.get("reason").and_then(Value::as_str))
                    .or_else(|| payload.get("message").and_then(Value::as_str))
                    .map(ToOwned::to_owned);
                let year = payload.get("year").and_then(|value| match value {
                    Value::Number(number) => number.as_i64().map(|raw| raw as i32),
                    Value::String(text) => text.parse::<i32>().ok(),
                    _ => None,
                });
                let entry = EnrichmentEntry {
                    provider: provider.clone(),
                    status: status.clone(),
                    confidence,
                    note,
                    mbid: payload
                        .get("recordingMbid")
                        .or_else(|| payload.get("mbid"))
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    release_mbid: payload
                        .get("releaseMbid")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    release_title: payload
                        .get("releaseTitle")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    release_date: payload
                        .get("releaseDate")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    match_score: match_score_raw.map(|score| {
                        if score > 1.0 {
                            (score / 100.0) as f32
                        } else {
                            score as f32
                        }
                    }),
                    listeners: payload.get("listeners").and_then(Value::as_i64),
                    play_count: payload
                        .get("playcount")
                        .or_else(|| payload.get("playCount"))
                        .and_then(Value::as_i64),
                    tags: payload
                        .get("tags")
                        .or_else(|| payload.get("top_tags"))
                        .and_then(Value::as_array)
                        .map(|items| {
                            items
                                .iter()
                                .filter_map(|item| item.as_str().map(ToOwned::to_owned))
                                .collect::<Vec<_>>()
                        })
                        .unwrap_or_default(),
                    wiki_summary: payload
                        .get("summary")
                        .or_else(|| payload.get("wikiSummary"))
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    year,
                    genres: payload
                        .get("genres")
                        .and_then(Value::as_array)
                        .map(|items| {
                            items
                                .iter()
                                .filter_map(|item| item.as_str().map(ToOwned::to_owned))
                                .collect::<Vec<_>>()
                        })
                        .unwrap_or_default(),
                    label: payload
                        .get("label")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    lyrics_url: payload
                        .get("url")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .map(ToOwned::to_owned),
                    has_lrc: (provider == "lrc_sidecar").then_some(status == "ok"),
                };

                let should_replace = match best_by_provider.get(&provider) {
                    None => true,
                    Some(existing) => {
                        let existing_rank = (
                            (existing.status == "ok") as i32,
                            (existing.confidence * 1000.0) as i32,
                        );
                        let next_rank = (
                            (entry.status == "ok") as i32,
                            (entry.confidence * 1000.0) as i32,
                        );
                        next_rank > existing_rank
                    }
                };
                if should_replace {
                    best_by_provider.insert(provider, entry);
                }
            }
        }

        let mut entries = best_by_provider.into_values().collect::<Vec<_>>();
        entries.sort_by(|left, right| {
            right
                .confidence
                .partial_cmp(&left.confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| left.provider.cmp(&right.provider))
        });

        let primary_mbid = entries
            .iter()
            .find(|entry| entry.provider == "musicbrainz" && entry.mbid.is_some())
            .and_then(|entry| entry.mbid.clone())
            .or_else(|| entries.iter().find_map(|entry| entry.mbid.clone()));
        let degraded_providers = entries
            .iter()
            .filter(|entry| entry.status != "ok")
            .map(|entry| entry.provider.clone())
            .collect::<Vec<_>>();
        let identity_confidence = entries
            .iter()
            .filter(|entry| {
                entry.mbid.is_some()
                    || entry.provider == "musicbrainz"
                    || entry.provider == "acoustid"
            })
            .map(|entry| entry.confidence)
            .fold(0.0_f32, f32::max);
        let has_ok = entries.iter().any(|entry| entry.status == "ok");
        let enrichment_state = if entries.is_empty() {
            "not_enriched".to_string()
        } else if has_ok && !degraded_providers.is_empty() {
            "degraded".to_string()
        } else if has_ok {
            "enriched".to_string()
        } else {
            "failed".to_string()
        };

        Ok(TrackEnrichmentResult {
            track_id: track.id,
            enrichment_state,
            entries,
            primary_mbid,
            identity_confidence,
            degraded_providers,
        })
    }

    pub fn get_artist_profile(&self, artist_name: String) -> LyraResult<Option<ArtistProfile>> {
        let conn = self.conn()?;
        let artist_name = artist_name.trim().to_string();
        if artist_name.is_empty() {
            return Ok(None);
        }

        let track_count: i64 = conn.query_row(
            "SELECT COUNT(*)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
            params![artist_name.as_str()],
            |row| row.get(0),
        )?;
        if track_count == 0 {
            return Ok(None);
        }

        let album_count: i64 = conn.query_row(
            "SELECT COUNT(DISTINCT al.id)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums al ON al.id = t.album_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
            params![artist_name.as_str()],
            |row| row.get(0),
        )?;

        let mut albums_stmt = conn.prepare(
            "SELECT COALESCE(al.title, ''), COUNT(*) AS c
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums al ON al.id = t.album_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
               AND trim(COALESCE(al.title, '')) != ''
             GROUP BY al.title
             ORDER BY c DESC, al.title ASC
             LIMIT 12",
        )?;
        let albums = albums_stmt
            .query_map(params![artist_name.as_str()], |row| row.get::<_, String>(0))?
            .filter_map(Result::ok)
            .collect::<Vec<_>>();

        let mut top_tracks_stmt = conn.prepare(
            "SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path,
                    COALESCE(t.duration_seconds, 0), t.genre, t.year, t.bpm, t.key_signature,
                    t.liked_at
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums al ON al.id = t.album_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
             ORDER BY t.id DESC
             LIMIT 16",
        )?;
        let top_tracks = top_tracks_stmt
            .query_map(params![artist_name.as_str()], |row| {
                Ok(TrackRecord {
                    id: row.get(0)?,
                    title: row.get(1)?,
                    artist: row.get(2)?,
                    album: row.get(3)?,
                    path: row.get(4)?,
                    duration_seconds: row.get(5)?,
                    genre: row.get(6)?,
                    year: row.get(7)?,
                    bpm: row.get(8)?,
                    key_signature: row.get(9)?,
                    liked: row.get::<_, Option<String>>(10)?.is_some(),
                    liked_at: row.get(10)?,
                })
            })?
            .filter_map(Result::ok)
            .collect::<Vec<_>>();

        let mut genres_stmt = conn.prepare(
            "SELECT t.genre, COUNT(*) AS c
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
               AND t.genre IS NOT NULL
               AND trim(t.genre) != ''
             GROUP BY t.genre
             ORDER BY c DESC
             LIMIT 8",
        )?;
        let genres = genres_stmt
            .query_map(params![artist_name.as_str()], |row| row.get::<_, String>(0))?
            .filter_map(Result::ok)
            .collect::<Vec<_>>();

        let mut bio: Option<String> = None;
        let mut image_url: Option<String> = None;
        let mut lastfm_url: Option<String> = None;

        let mut enrich_stmt = conn.prepare(
            "SELECT ec.provider, ec.payload_json
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             JOIN enrich_cache ec
               ON ec.lookup_key = lower(trim(COALESCE(ar.name, ''))) || '::' || lower(trim(COALESCE(t.title, '')))
               OR ec.lookup_key = COALESCE(t.path, '')
             WHERE (
                    lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
                   )
             ORDER BY ec.fetched_at DESC
             LIMIT 250",
        )?;
        let enrich_rows = enrich_stmt.query_map(params![artist_name.as_str()], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?;
        for row in enrich_rows.filter_map(Result::ok) {
            let (provider, payload_json) = row;
            let Ok(payload) = serde_json::from_str::<Value>(&payload_json) else {
                continue;
            };
            if provider == "lastfm" {
                if bio.is_none() {
                    bio = payload
                        .get("summary")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|v| !v.is_empty())
                        .map(ToOwned::to_owned);
                }
                if lastfm_url.is_none() {
                    lastfm_url = payload
                        .get("url")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|v| !v.is_empty())
                        .map(ToOwned::to_owned);
                }
            }
            if provider == "genius" && image_url.is_none() {
                image_url = payload
                    .get("artUrl")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|v| !v.is_empty())
                    .map(ToOwned::to_owned);
            }
            if provider == "discogs" && image_url.is_none() {
                image_url = payload
                    .get("coverImage")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|v| !v.is_empty())
                    .map(ToOwned::to_owned);
            }
            if bio.is_some() && image_url.is_some() && lastfm_url.is_some() {
                break;
            }
        }

        let mut conn_stmt = conn.prepare(
            "SELECT COALESCE(ar2.name, ''), COUNT(*) AS strength
             FROM playback_history p1
             JOIN playback_history p2
               ON p1.id != p2.id
              AND abs(strftime('%s', p1.ts) - strftime('%s', p2.ts)) <= 1800
             JOIN tracks t1 ON t1.id = p1.track_id
             LEFT JOIN artists ar1 ON ar1.id = t1.artist_id
             JOIN tracks t2 ON t2.id = p2.track_id
             LEFT JOIN artists ar2 ON ar2.id = t2.artist_id
             WHERE lower(trim(COALESCE(ar1.name, ''))) = lower(trim(?1))
               AND lower(trim(COALESCE(ar2.name, ''))) != lower(trim(?1))
               AND trim(COALESCE(ar2.name, '')) != ''
             GROUP BY ar2.name
             ORDER BY strength DESC
             LIMIT 12",
        )?;
        let connections = conn_stmt
            .query_map(params![artist_name.as_str()], |row| {
                Ok(ArtistConnection {
                    artist: row.get(0)?,
                    score: row.get(1)?,
                })
            })?
            .filter_map(Result::ok)
            .collect::<Vec<_>>();

        let mut provenance_by_provider: std::collections::HashMap<
            String,
            commands::EnrichmentEntry,
        > = std::collections::HashMap::new();
        let mut primary_mbid: Option<String> = None;
        let mut identity_confidence = 0.0_f32;
        for track in top_tracks.iter().take(8) {
            let enrichment = self.build_track_enrichment_result(&conn, track)?;
            if primary_mbid.is_none() {
                primary_mbid = enrichment.primary_mbid.clone();
            }
            identity_confidence = identity_confidence.max(enrichment.identity_confidence);
            for entry in enrichment.entries {
                let should_replace = match provenance_by_provider.get(&entry.provider) {
                    None => true,
                    Some(existing) => {
                        let existing_rank = (
                            (existing.status == "ok") as i32,
                            (existing.confidence * 1000.0) as i32,
                        );
                        let next_rank = (
                            (entry.status == "ok") as i32,
                            (entry.confidence * 1000.0) as i32,
                        );
                        next_rank > existing_rank
                    }
                };
                if should_replace {
                    provenance_by_provider.insert(entry.provider.clone(), entry);
                }
            }
        }
        let mut provenance = provenance_by_provider.into_values().collect::<Vec<_>>();
        provenance.sort_by(|left, right| {
            right
                .confidence
                .partial_cmp(&left.confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| left.provider.cmp(&right.provider))
        });
        if bio.is_none() {
            bio = provenance
                .iter()
                .find_map(|entry| entry.wiki_summary.clone())
                .filter(|value| !value.is_empty());
        }

        Ok(Some(ArtistProfile {
            artist: artist_name,
            track_count,
            album_count,
            albums,
            genres,
            bio,
            image_url,
            lastfm_url,
            primary_mbid,
            identity_confidence,
            provenance,
            top_tracks,
            connections,
        }))
    }

    pub fn play_artist(&self, artist_name: String) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let track_ids = library::list_track_ids_for_artist(&conn, artist_name.as_str(), 500)?;
        let first = track_ids
            .first()
            .copied()
            .ok_or(LyraError::NotFound("artist tracks"))?;
        queue::replace_queue(&conn, &track_ids)?;
        self.play_track(first)
    }

    pub fn play_album(
        &self,
        artist_name: String,
        album_title: String,
    ) -> LyraResult<PlaybackState> {
        let conn = self.conn()?;
        let track_ids = library::list_track_ids_for_album(
            &conn,
            artist_name.as_str(),
            album_title.as_str(),
            500,
        )?;
        let first = track_ids
            .first()
            .copied()
            .ok_or(LyraError::NotFound("album tracks"))?;
        queue::replace_queue(&conn, &track_ids)?;
        self.play_track(first)
    }

    /// Return structured enrichment data for a single track, grouped by provider with
    /// confidence + MBID metadata extracted from cached payloads.
    pub fn get_track_enrichment(
        &self,
        track_id: i64,
    ) -> LyraResult<commands::TrackEnrichmentResult> {
        let conn = self.conn()?;
        let track =
            library::get_track_by_id(&conn, track_id)?.ok_or(LyraError::NotFound("track"))?;
        self.build_track_enrichment_result(&conn, &track)
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
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get::<_, Option<String>>(3)?.unwrap_or_default(),
                ))
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
            let cached_before = enrichment::get_enrich_cache(
                &conn,
                "musicbrainz",
                &format!(
                    "{}::{}",
                    artist.trim().to_ascii_lowercase(),
                    title.trim().to_ascii_lowercase()
                ),
            )?
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

fn create_dir_all_if_missing(path: &Path) -> std::io::Result<()> {
    fs::create_dir_all(path)
}

fn is_path_writable(path: &Path) -> bool {
    if fs::create_dir_all(path).is_err() {
        return false;
    }
    let probe = path.join(".lyra-write-probe");
    match fs::write(&probe, b"ok") {
        Ok(()) => {
            let _ = fs::remove_file(probe);
            true
        }
        Err(_) => false,
    }
}
