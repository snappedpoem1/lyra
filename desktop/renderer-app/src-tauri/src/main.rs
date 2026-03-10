use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;
use std::time::Duration;

#[cfg(target_os = "windows")]
mod smtc;

use lyra_core::commands::{
    AcquisitionEventPayload, AcquisitionLead, AcquisitionLeadHandoffReport, AcquisitionPreflight,
    AcquisitionQueueItem, AppShellState, ArtistProfile, AudioOutputDevice, BootstrapPayload,
    ComposedPlaylistDraft, ComposerDiagnosticEntry, ComposerResponse, ComposerRunDetail,
    ComposerRunRecord, CurationLogEntry, DiscoverySession, DuplicateCluster, ExplainPayload,
    GeneratedPlaylist, GraphStats, LegacyImportReport, LibraryCleanupPreview, NativeCapabilities,
    PlaybackEvent, PlaybackState, PlaylistDetail, PlaylistSummary, PlaylistTrackReasonRecord,
    ProviderConfigRecord, ProviderHealth, ProviderValidationResult, QueueItemRecord,
    RecentPlayRecord, RecommendationBundle, RecommendationResult, RelatedArtist,
    RouteFeedbackPayload, ScanJobRecord, SettingsPayload, SpotifyGapSummary, SteerPayload,
    TasteMemorySnapshot, TasteProfile, TrackDetail, TrackEnrichmentResult, TrackRecord, TrackScores,
};
use lyra_core::classifier::{ClassifyResult, LibrarySummary};
use lyra_core::logging::initialize_logging;
use lyra_core::taste_prioritizer::{PrioritizeStats, QueueItem};
use lyra_core::validator::ValidationResult;
use lyra_core::LyraCore;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

#[derive(Clone)]
struct AppState {
    core: LyraCore,
    sleep_until: Arc<std::sync::Mutex<Option<std::time::Instant>>>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct WindowStateRecord {
    width: f64,
    height: f64,
    x: i32,
    y: i32,
    maximized: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderUpdatePayload {
    provider_key: String,
    enabled: bool,
    values: Value,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LegacyImportPayload {
    env_path: Option<String>,
    legacy_db_path: Option<String>,
}

fn window_state_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|path| path.join("window-state.json"))
}

fn emit_payload<T: Serialize + ?Sized>(app: &AppHandle, event: &str, payload: &T) {
    let _ = app.emit(event, payload);
}

fn emit_shell(app: &AppHandle, core: &LyraCore) {
    if let Ok(shell) = core.get_app_shell_state() {
        emit_payload(app, "lyra://bootstrap", &shell);
    }
}

fn emit_queue(app: &AppHandle, payload: &[QueueItemRecord]) {
    emit_payload(app, "lyra://queue-updated", payload);
}

fn emit_acquisition(app: &AppHandle, core: &LyraCore, latest_item_id: Option<i64>) {
    if let Ok(queue) = core.get_acquisition_queue(None) {
        let payload = AcquisitionEventPayload {
            queue,
            worker_running: core.acquisition_worker_status().unwrap_or(false),
            latest_item_id,
        };
        emit_payload(app, "lyra://acquisition-updated", &payload);
    }
}

fn emit_playback(app: &AppHandle, payload: &PlaybackState) {
    emit_payload(app, "lyra://playback-updated", payload);
}

fn emit_settings(app: &AppHandle, payload: &SettingsPayload) {
    emit_payload(app, "lyra://settings-updated", payload);
}

fn emit_providers(app: &AppHandle, payload: &[ProviderConfigRecord]) {
    emit_payload(app, "lyra://provider-updated", payload);
}

fn toggle_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(true) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

fn persist_window_state(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let Ok(position) = window.outer_position() else {
        return;
    };
    let record = WindowStateRecord {
        width: size.width as f64,
        height: size.height as f64,
        x: position.x,
        y: position.y,
        maximized: window.is_maximized().unwrap_or(false),
    };
    if let Some(path) = window_state_path(app) {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(contents) = serde_json::to_string_pretty(&record) {
            let _ = fs::write(path, contents);
        }
    }
}

fn restore_window_state(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Some(path) = window_state_path(app) else {
        return;
    };
    let Ok(contents) = fs::read_to_string(path) else {
        return;
    };
    let Ok(record) = serde_json::from_str::<WindowStateRecord>(&contents) else {
        return;
    };
    let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
        width: record.width.max(960.0) as u32,
        height: record.height.max(720.0) as u32,
    }));
    let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
        x: record.x,
        y: record.y,
    }));
    if record.maximized {
        let _ = window.maximize();
    }
}

fn create_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let show = MenuItem::with_id(app, "show", "Show / Hide", true, None::<&str>)?;
    let play_pause = MenuItem::with_id(app, "play_pause", "Play / Pause", true, None::<&str>)?;
    let previous = MenuItem::with_id(app, "previous", "Previous", true, None::<&str>)?;
    let next = MenuItem::with_id(app, "next", "Next", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    Menu::with_items(
        app,
        &[&show, &play_pause, &previous, &next, &separator, &quit],
    )
}

fn create_tray(app: &AppHandle, state: &AppState) -> tauri::Result<()> {
    let tray_menu = create_menu(app)?;
    let icon = app.default_window_icon().cloned();
    let mut builder = TrayIconBuilder::with_id("lyra-tray").menu(&tray_menu);
    if let Some(icon) = icon {
        builder = builder.icon(icon);
    }
    let state_clone = state.clone();
    let _tray = builder
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "show" => toggle_main_window(app),
            "play_pause" => {
                if let Ok(playback) = state_clone.core.toggle_playback() {
                    emit_playback(app, &playback);
                }
            }
            "previous" => {
                if let Ok(playback) = state_clone.core.play_previous() {
                    emit_playback(app, &playback);
                }
            }
            "next" => {
                if let Ok(playback) = state_clone.core.play_next() {
                    emit_playback(app, &playback);
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button,
                button_state,
                ..
            } = event
            {
                if button == tauri::tray::MouseButton::Left
                    && button_state == tauri::tray::MouseButtonState::Up
                {
                    toggle_main_window(tray.app_handle());
                }
            }
        })
        .build(app)?;
    Ok(())
}

fn register_shortcuts(app: &AppHandle, state: &AppState) {
    let shortcuts = [
        ("MediaPlayPause", "play-pause"),
        ("MediaNextTrack", "next"),
        ("MediaPreviousTrack", "previous"),
    ];
    for (accelerator, action) in shortcuts {
        let state_clone = state.clone();
        let _ = app
            .global_shortcut()
            .on_shortcut(accelerator, move |shortcut_app, _, event| {
                if event.state() != ShortcutState::Pressed {
                    return;
                }
                let playback = match action {
                    "play-pause" => state_clone.core.toggle_playback(),
                    "next" => state_clone.core.play_next(),
                    "previous" => state_clone.core.play_previous(),
                    _ => return,
                };
                if let Ok(payload) = playback {
                    emit_payload(
                        shortcut_app,
                        "lyra://native-action",
                        &serde_json::json!({ "action": action }),
                    );
                    emit_playback(shortcut_app, &payload);
                }
            });
    }
}

#[tauri::command]
fn bootstrap_app(state: State<'_, AppState>) -> Result<BootstrapPayload, String> {
    state
        .core
        .bootstrap_app()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn get_app_shell_state(state: State<'_, AppState>) -> Result<AppShellState, String> {
    state
        .core
        .get_app_shell_state()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn list_tracks(
    state: State<'_, AppState>,
    query: Option<String>,
    sort: Option<String>,
) -> Result<Vec<TrackRecord>, String> {
    state
        .core
        .list_tracks(query, sort)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn get_library_overview(
    state: State<'_, AppState>,
) -> Result<lyra_core::commands::LibraryOverview, String> {
    state
        .core
        .get_library_overview()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn list_library_roots(
    state: State<'_, AppState>,
) -> Result<Vec<lyra_core::commands::LibraryRootRecord>, String> {
    state
        .core
        .list_library_roots()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn add_library_root(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<Vec<lyra_core::commands::LibraryRootRecord>, String> {
    let payload = state
        .core
        .add_library_root(path)
        .map_err(|error| error.to_string())?;
    emit_payload(&app, "lyra://library-updated", &payload);
    Ok(payload)
}

#[tauri::command]
fn remove_library_root(
    app: AppHandle,
    state: State<'_, AppState>,
    root_id: i64,
) -> Result<Vec<lyra_core::commands::LibraryRootRecord>, String> {
    let payload = state
        .core
        .remove_library_root(root_id)
        .map_err(|error| error.to_string())?;
    emit_payload(&app, "lyra://library-updated", &payload);
    Ok(payload)
}

#[tauri::command]
fn start_library_scan(app: AppHandle, state: State<'_, AppState>) -> Result<ScanJobRecord, String> {
    let job = state
        .core
        .create_scan_job()
        .map_err(|error| error.to_string())?;
    let core = state.core.clone();
    let app_handle = app.clone();
    let event_handle = app.clone();
    thread::spawn(move || {
        let _ = core.run_scan_job(job.id, move |event, payload| {
            let _ = event_handle.emit(event, payload);
        });
        emit_shell(&app_handle, &core);
        // Background enrichment pass: enrich up to 30 newly-imported tracks.
        // Runs after the shell has already been updated, fully in the background.
        let _ = core.enrich_unenriched_tracks(30);
    });
    Ok(job)
}

#[tauri::command]
fn enrich_library(state: State<'_, AppState>) -> Result<(), String> {
    let core = state.core.clone();
    thread::spawn(move || {
        let _ = core.enrich_unenriched_tracks(50);
    });
    Ok(())
}

#[tauri::command]
fn refresh_track_enrichment(
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<serde_json::Value, String> {
    state
        .core
        .refresh_track_enrichment(track_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn validate_provider(
    state: State<'_, AppState>,
    provider_key: String,
) -> Result<ProviderValidationResult, String> {
    state
        .core
        .validate_provider(provider_key)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn keyring_save(
    state: State<'_, AppState>,
    provider_key: String,
    key_name: String,
    secret: String,
) -> Result<(), String> {
    state.core.keyring_save(provider_key, key_name, secret)
}

#[tauri::command]
fn keyring_load(
    state: State<'_, AppState>,
    provider_key: String,
    key_name: String,
) -> Result<Option<String>, String> {
    state.core.keyring_load(provider_key, key_name)
}

#[tauri::command]
fn keyring_delete(
    state: State<'_, AppState>,
    provider_key: String,
    key_name: String,
) -> Result<(), String> {
    state.core.keyring_delete(provider_key, key_name)
}

#[tauri::command]
fn toggle_like(state: State<'_, AppState>, track_id: i64) -> Result<bool, String> {
    state.core.toggle_like(track_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_liked_tracks(state: State<'_, AppState>) -> Result<Vec<TrackRecord>, String> {
    state.core.list_liked_tracks().map_err(|e| e.to_string())
}

/// Set a sleep timer to stop playback after `minutes` minutes.
/// Pass 0 to cancel.
#[tauri::command]
fn list_recent_plays(
    state: State<'_, AppState>,
    limit: Option<i64>,
) -> Result<Vec<RecentPlayRecord>, String> {
    state
        .core
        .list_recent_plays(limit)
        .map_err(|e| e.to_string())
}

/// Scan a .env file and save all credential-like values to the OS keychain.
/// Returns { saved, skipped }.
#[tauri::command]
fn backup_env_to_keychain(
    state: State<'_, AppState>,
    env_path: String,
) -> Result<serde_json::Value, String> {
    let (saved, skipped) = state.core.backup_env_to_keychain(env_path)?;
    Ok(serde_json::json!({ "saved": saved, "skipped": skipped }))
}

#[tauri::command]
fn load_env_credential(
    state: State<'_, AppState>,
    key_name: String,
) -> Result<Option<String>, String> {
    state.core.load_env_credential(key_name)
}

#[tauri::command]
fn set_sleep_timer(state: State<'_, AppState>, minutes: u32) -> Result<(), String> {
    let mut guard = state.sleep_until.lock().map_err(|e| e.to_string())?;
    if minutes == 0 {
        *guard = None;
    } else {
        *guard = Some(std::time::Instant::now() + Duration::from_secs(minutes as u64 * 60));
    }
    Ok(())
}

/// Returns seconds remaining in the sleep timer, or None if not set.
#[tauri::command]
fn get_sleep_timer(state: State<'_, AppState>) -> Result<Option<u64>, String> {
    let guard = state.sleep_until.lock().map_err(|e| e.to_string())?;
    Ok(guard.map(|t| {
        let now = std::time::Instant::now();
        if t > now {
            (t - now).as_secs()
        } else {
            0
        }
    }))
}

#[tauri::command]
fn lastfm_get_session(
    state: State<'_, AppState>,
    api_key: String,
    api_secret: String,
    username: String,
    password: String,
) -> Result<String, String> {
    state
        .core
        .lastfm_get_session(api_key, api_secret, username, password)
}

#[tauri::command]
fn get_scan_jobs(state: State<'_, AppState>) -> Result<Vec<ScanJobRecord>, String> {
    state
        .core
        .get_scan_jobs()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn list_playlists(state: State<'_, AppState>) -> Result<Vec<PlaylistSummary>, String> {
    state
        .core
        .list_playlists()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn get_playlist_detail(
    state: State<'_, AppState>,
    playlist_id: i64,
) -> Result<PlaylistDetail, String> {
    state
        .core
        .get_playlist_detail(playlist_id)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn create_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .create_playlist(name)
        .map_err(|error| error.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn rename_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
    name: String,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .rename_playlist(playlist_id, name)
        .map_err(|error| error.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn delete_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
) -> Result<Vec<PlaylistSummary>, String> {
    let payload = state
        .core
        .delete_playlist(playlist_id)
        .map_err(|error| error.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn enqueue_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
) -> Result<Vec<QueueItemRecord>, String> {
    let payload = state
        .core
        .enqueue_playlist(playlist_id)
        .map_err(|error| error.to_string())?;
    emit_queue(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn enqueue_tracks(
    app: AppHandle,
    state: State<'_, AppState>,
    track_ids: Vec<i64>,
) -> Result<Vec<QueueItemRecord>, String> {
    let payload = state
        .core
        .enqueue_tracks(track_ids)
        .map_err(|error| error.to_string())?;
    emit_queue(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn get_queue(state: State<'_, AppState>) -> Result<Vec<QueueItemRecord>, String> {
    state.core.get_queue().map_err(|error| error.to_string())
}

#[tauri::command]
fn move_queue_item(
    app: AppHandle,
    state: State<'_, AppState>,
    queue_item_id: i64,
    new_position: i64,
) -> Result<Vec<QueueItemRecord>, String> {
    let payload = state
        .core
        .move_queue_item(queue_item_id, new_position)
        .map_err(|error| error.to_string())?;
    emit_queue(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn remove_queue_item(
    app: AppHandle,
    state: State<'_, AppState>,
    queue_item_id: i64,
) -> Result<Vec<QueueItemRecord>, String> {
    let payload = state
        .core
        .remove_queue_item(queue_item_id)
        .map_err(|error| error.to_string())?;
    emit_queue(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn clear_queue(app: AppHandle, state: State<'_, AppState>) -> Result<Vec<QueueItemRecord>, String> {
    let payload = state
        .core
        .clear_queue()
        .map_err(|error| error.to_string())?;
    emit_queue(&app, &payload);
    if let Ok(playback) = state.core.get_playback_state() {
        emit_playback(&app, &playback);
    }
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn get_playback_state(state: State<'_, AppState>) -> Result<PlaybackState, String> {
    state
        .core
        .get_playback_state()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn play_track(
    app: AppHandle,
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .play_track(track_id)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn play_artist(
    app: AppHandle,
    state: State<'_, AppState>,
    artist_name: String,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .play_artist(artist_name)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn play_album(
    app: AppHandle,
    state: State<'_, AppState>,
    artist_name: String,
    album_title: String,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .play_album(artist_name, album_title)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn play_queue_index(
    app: AppHandle,
    state: State<'_, AppState>,
    index: i64,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .play_queue_index(index)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn toggle_playback(app: AppHandle, state: State<'_, AppState>) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .toggle_playback()
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn stop_playback(app: AppHandle, state: State<'_, AppState>) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .stop_playback()
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn list_audio_devices(state: State<'_, AppState>) -> Vec<AudioOutputDevice> {
    state.core.list_audio_devices()
}

#[tauri::command]
fn set_output_device(
    app: AppHandle,
    state: State<'_, AppState>,
    device_name: Option<String>,
) -> Result<SettingsPayload, String> {
    let payload = state
        .core
        .set_output_device(device_name)
        .map_err(|e| e.to_string())?;
    emit_settings(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn enrich_track(state: State<'_, AppState>, track_id: i64) -> Result<serde_json::Value, String> {
    state.core.enrich_track(track_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn play_next(app: AppHandle, state: State<'_, AppState>) -> Result<PlaybackState, String> {
    let payload = state.core.play_next().map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn play_previous(app: AppHandle, state: State<'_, AppState>) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .play_previous()
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn seek_to(
    app: AppHandle,
    state: State<'_, AppState>,
    position_seconds: f64,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .seek_to(position_seconds)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn set_volume(
    app: AppHandle,
    state: State<'_, AppState>,
    volume: f64,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .set_volume(volume)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn set_repeat_mode(
    app: AppHandle,
    state: State<'_, AppState>,
    repeat_mode: String,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .set_repeat_mode(repeat_mode)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn set_shuffle(
    app: AppHandle,
    state: State<'_, AppState>,
    shuffle: bool,
) -> Result<PlaybackState, String> {
    let payload = state
        .core
        .set_shuffle(shuffle)
        .map_err(|error| error.to_string())?;
    emit_playback(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn get_settings(state: State<'_, AppState>) -> Result<SettingsPayload, String> {
    state.core.get_settings().map_err(|error| error.to_string())
}

#[tauri::command]
fn update_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    settings: SettingsPayload,
) -> Result<SettingsPayload, String> {
    let payload = state
        .core
        .update_settings(settings)
        .map_err(|error| error.to_string())?;
    emit_settings(&app, &payload);
    Ok(payload)
}

#[tauri::command]
fn list_provider_configs(state: State<'_, AppState>) -> Result<Vec<ProviderConfigRecord>, String> {
    state
        .core
        .list_provider_configs()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn update_provider_config(
    app: AppHandle,
    state: State<'_, AppState>,
    payload: ProviderUpdatePayload,
) -> Result<Vec<ProviderConfigRecord>, String> {
    let providers = state
        .core
        .update_provider_config(payload.provider_key, payload.enabled, payload.values)
        .map_err(|error| error.to_string())?;
    emit_providers(&app, &providers);
    Ok(providers)
}

#[tauri::command]
fn run_legacy_import(
    app: AppHandle,
    state: State<'_, AppState>,
    payload: LegacyImportPayload,
) -> Result<LegacyImportReport, String> {
    let report = state
        .core
        .run_legacy_import(payload.env_path, payload.legacy_db_path)
        .map_err(|error| error.to_string())?;
    emit_shell(&app, &state.core);
    Ok(report)
}

#[tauri::command]
fn get_native_capabilities(state: State<'_, AppState>) -> NativeCapabilities {
    state.core.get_native_capabilities()
}

#[tauri::command]
fn get_track_scores(
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<Option<TrackScores>, String> {
    state
        .core
        .get_track_scores(track_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_taste_profile(state: State<'_, AppState>) -> Result<TasteProfile, String> {
    state.core.get_taste_profile().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_recommendations(
    state: State<'_, AppState>,
    limit: Option<usize>,
) -> Result<Vec<RecommendationResult>, String> {
    state
        .core
        .get_recommendations(limit.unwrap_or(20))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_recommendation_bundle(
    state: State<'_, AppState>,
    limit: Option<usize>,
) -> Result<RecommendationBundle, String> {
    state
        .core
        .get_recommendation_bundle(limit.unwrap_or(20))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn explain_recommendation(
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<ExplainPayload, String> {
    state
        .core
        .explain_recommendation(track_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn enqueue_recommendation_leads(
    app: AppHandle,
    state: State<'_, AppState>,
    leads: Vec<AcquisitionLead>,
) -> Result<AcquisitionLeadHandoffReport, String> {
    let report = state
        .core
        .enqueue_recommendation_leads(leads)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    emit_acquisition(&app, &state.core, None);
    Ok(report)
}

#[tauri::command]
fn get_acquisition_queue(
    state: State<'_, AppState>,
    status_filter: Option<String>,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    state
        .core
        .get_acquisition_queue(status_filter)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn add_to_acquisition_queue(
    app: AppHandle,
    state: State<'_, AppState>,
    artist: String,
    title: String,
    album: Option<String>,
    source: Option<String>,
    target_root_id: Option<i64>,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .add_to_acquisition_queue(artist, title, album, source, target_root_id)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, payload.last().map(|item| item.id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn update_acquisition_item(
    app: AppHandle,
    state: State<'_, AppState>,
    id: i64,
    status: String,
    error: Option<String>,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .update_acquisition_item(id, status, error)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, Some(id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn process_acquisition_queue(app: AppHandle, state: State<'_, AppState>) -> Result<bool, String> {
    let processed = state
        .core
        .process_acquisition_queue_with_callback({
            let app = app.clone();
            let core = state.core.clone();
            move |item_id| {
                emit_acquisition(&app, &core, Some(item_id));
                emit_shell(&app, &core);
            }
        })
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, None);
    emit_shell(&app, &state.core);
    Ok(processed)
}

#[tauri::command]
fn clear_completed_acquisition(app: AppHandle, state: State<'_, AppState>) -> Result<i64, String> {
    let removed = state
        .core
        .clear_completed_acquisition()
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, None);
    emit_shell(&app, &state.core);
    Ok(removed)
}

#[tauri::command]
fn retry_failed_acquisition(app: AppHandle, state: State<'_, AppState>) -> Result<i64, String> {
    let retried = state
        .core
        .retry_failed_acquisition()
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, None);
    emit_shell(&app, &state.core);
    Ok(retried)
}

#[tauri::command]
fn set_acquisition_priority(
    app: AppHandle,
    state: State<'_, AppState>,
    id: i64,
    priority_score: f64,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .set_acquisition_priority(id, priority_score)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, Some(id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn move_acquisition_queue_item(
    app: AppHandle,
    state: State<'_, AppState>,
    id: i64,
    new_position: i64,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .move_acquisition_queue_item(id, new_position)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, Some(id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn set_acquisition_target_root(
    app: AppHandle,
    state: State<'_, AppState>,
    id: i64,
    target_root_id: Option<i64>,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .set_acquisition_target_root(id, target_root_id)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, Some(id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn cancel_acquisition_item(
    app: AppHandle,
    state: State<'_, AppState>,
    id: i64,
    detail: Option<String>,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let payload = state
        .core
        .cancel_acquisition_item(id, detail)
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, Some(id));
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn acquisition_preflight(state: State<'_, AppState>) -> Result<AcquisitionPreflight, String> {
    state
        .core
        .acquisition_preflight()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn start_acquisition_worker(app: AppHandle, state: State<'_, AppState>) -> Result<bool, String> {
    let started = state
        .core
        .start_acquisition_worker_with_callback({
            let app = app.clone();
            let core = state.core.clone();
            move |item_id| {
                emit_acquisition(&app, &core, Some(item_id));
                emit_shell(&app, &core);
            }
        })
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, None);
    Ok(started)
}

#[tauri::command]
fn stop_acquisition_worker(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    state
        .core
        .stop_acquisition_worker()
        .map_err(|e| e.to_string())?;
    emit_acquisition(&app, &state.core, None);
    Ok(())
}

#[tauri::command]
fn acquisition_worker_status(state: State<'_, AppState>) -> Result<bool, String> {
    state
        .core
        .acquisition_worker_status()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn run_diagnostics(
    state: State<'_, AppState>,
) -> Result<lyra_core::commands::DiagnosticsReport, String> {
    state.core.run_diagnostics().map_err(|e| e.to_string())
}

#[tauri::command]
fn list_playback_history(
    state: State<'_, AppState>,
    limit: Option<i64>,
) -> Result<Vec<PlaybackEvent>, String> {
    state
        .core
        .list_playback_history(limit)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn record_playback_event(
    state: State<'_, AppState>,
    track_id: i64,
    completion_rate: f64,
    context: Option<String>,
) -> Result<(), String> {
    state
        .core
        .record_playback_event(track_id, completion_rate, context)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_track_detail(
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<Option<TrackDetail>, String> {
    state
        .core
        .get_track_detail(track_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_artist_profile(
    state: State<'_, AppState>,
    artist_name: String,
) -> Result<Option<ArtistProfile>, String> {
    state
        .core
        .get_artist_profile(artist_name)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn classify_track(state: State<'_, AppState>, track_id: i64) -> Result<ClassifyResult, String> {
    state.core.classify_track(track_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn classify_library(state: State<'_, AppState>, limit: usize) -> Result<LibrarySummary, String> {
    state.core.classify_library(limit).map_err(|e| e.to_string())
}

#[tauri::command]
fn validate_track_text(state: State<'_, AppState>, artist: String, title: String) -> ValidationResult {
    state.core.validate_track_text(&artist, &title)
}

#[tauri::command]
fn prioritize_acquisition_queue(state: State<'_, AppState>, limit: usize) -> Result<PrioritizeStats, String> {
    state.core.prioritize_acquisition_queue(limit).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_priority_batch(state: State<'_, AppState>, limit: usize) -> Result<Vec<QueueItem>, String> {
    state.core.get_priority_batch(limit).map_err(|e| e.to_string())
}

#[tauri::command]
fn find_duplicates(state: State<'_, AppState>) -> Result<Vec<DuplicateCluster>, String> {
    state.core.find_duplicates().map_err(|e| e.to_string())
}

#[tauri::command]
fn list_provider_health(state: State<'_, AppState>) -> Result<Vec<ProviderHealth>, String> {
    state.core.list_provider_health().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_provider_health(
    state: State<'_, AppState>,
    provider_key: String,
) -> Result<ProviderHealth, String> {
    state
        .core
        .get_provider_health(provider_key)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn record_provider_event(
    state: State<'_, AppState>,
    provider_key: String,
    success: bool,
) -> Result<ProviderHealth, String> {
    state
        .core
        .record_provider_event(provider_key, success)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn reset_provider_health(
    state: State<'_, AppState>,
    provider_key: String,
) -> Result<Vec<ProviderHealth>, String> {
    state
        .core
        .reset_provider_health(provider_key)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn add_track_to_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
    track_id: i64,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .add_track_to_playlist(playlist_id, track_id)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn remove_track_from_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
    track_id: i64,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .remove_track_from_playlist(playlist_id, track_id)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn reorder_playlist_item(
    app: AppHandle,
    state: State<'_, AppState>,
    playlist_id: i64,
    track_id: i64,
    new_position: i64,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .reorder_playlist_item(playlist_id, track_id, new_position)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

// ── G-061: Enrichment Provenance ─────────────────────────────────────────────

#[tauri::command]
fn get_track_enrichment(
    state: State<'_, AppState>,
    track_id: i64,
) -> Result<TrackEnrichmentResult, String> {
    state
        .core
        .get_track_enrichment(track_id)
        .map_err(|e| e.to_string())
}

// ── G-062: Curation Workflows ─────────────────────────────────────────────────

#[tauri::command]
fn resolve_duplicate_cluster(
    state: State<'_, AppState>,
    keep_track_id: i64,
    remove_track_ids: Vec<i64>,
) -> Result<(), String> {
    state
        .core
        .resolve_duplicate_cluster(keep_track_id, remove_track_ids)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_curation_log(state: State<'_, AppState>) -> Result<Vec<CurationLogEntry>, String> {
    state.core.get_curation_log().map_err(|e| e.to_string())
}

#[tauri::command]
fn undo_curation(state: State<'_, AppState>, log_id: i64) -> Result<(), String> {
    state.core.undo_curation(log_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn preview_library_cleanup(state: State<'_, AppState>) -> Result<LibraryCleanupPreview, String> {
    state
        .core
        .preview_library_cleanup()
        .map_err(|e| e.to_string())
}

// ── G-063: Playlist Intelligence ─────────────────────────────────────────────

#[tauri::command]
fn compose_playlist_draft(
    state: State<'_, AppState>,
    prompt: String,
    track_count: usize,
) -> Result<ComposedPlaylistDraft, String> {
    state
        .core
        .compose_playlist_draft(prompt, track_count)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn compose_with_lyra(
    state: State<'_, AppState>,
    prompt: String,
    track_count: usize,
    steer: Option<SteerPayload>,
) -> Result<ComposerResponse, String> {
    state
        .core
        .compose_with_lyra(prompt, track_count, steer)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_composer_diagnostics(
    state: State<'_, AppState>,
    limit: Option<usize>,
) -> Result<Vec<ComposerDiagnosticEntry>, String> {
    state
        .core
        .get_composer_diagnostics(limit.unwrap_or(20))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_recent_composer_runs(
    state: State<'_, AppState>,
    limit: Option<usize>,
) -> Result<Vec<ComposerRunRecord>, String> {
    state
        .core
        .get_recent_composer_runs(limit.unwrap_or(12))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_composer_run(state: State<'_, AppState>, run_id: i64) -> Result<ComposerRunDetail, String> {
    state
        .core
        .get_composer_run(run_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_spotify_gap_summary(
    state: State<'_, AppState>,
    limit: Option<usize>,
) -> Result<SpotifyGapSummary, String> {
    state
        .core
        .get_spotify_gap_summary(limit.unwrap_or(8))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn save_composed_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    draft: ComposedPlaylistDraft,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .save_composed_playlist(name, draft)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn record_route_feedback(
    app: AppHandle,
    state: State<'_, AppState>,
    payload: RouteFeedbackPayload,
) -> Result<TasteMemorySnapshot, String> {
    let snapshot = state
        .core
        .record_route_feedback(payload)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(snapshot)
}

#[tauri::command]
fn generate_act_playlist(
    state: State<'_, AppState>,
    intent: String,
    track_count: usize,
) -> Result<GeneratedPlaylist, String> {
    state
        .core
        .generate_act_playlist(intent, track_count)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn save_generated_playlist(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    playlist: GeneratedPlaylist,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .save_generated_playlist(name, playlist)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

#[tauri::command]
fn get_playlist_track_reasons(
    state: State<'_, AppState>,
    playlist_id: i64,
) -> Result<Vec<PlaylistTrackReasonRecord>, String> {
    state
        .core
        .get_playlist_track_reasons(playlist_id)
        .map_err(|e| e.to_string())
}

// ── Acquisition Seeding ───────────────────────────────────────────────────────

#[tauri::command]
fn seed_acquisition_from_spotify_library(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<usize, String> {
    let count = state
        .core
        .seed_acquisition_from_spotify_library()
        .map_err(|e| e.to_string())?;
    if count > 0 {
        emit_shell(&app, &state.core);
    }
    Ok(count)
}

#[tauri::command]
fn bulk_add_to_acquisition_queue(
    app: AppHandle,
    state: State<'_, AppState>,
    // Vec of [artist, title, album_or_null]
    entries: Vec<Vec<serde_json::Value>>,
    source: String,
) -> Result<Vec<AcquisitionQueueItem>, String> {
    let parsed: Vec<(String, String, Option<String>)> = entries
        .into_iter()
        .filter_map(|entry| {
            let artist = entry.first()?.as_str()?.to_string();
            let title = entry.get(1)?.as_str()?.to_string();
            let album = entry.get(2).and_then(|v| v.as_str()).map(|s| s.to_string());
            Some((artist, title, album))
        })
        .collect();
    let items = state
        .core
        .bulk_add_to_acquisition_queue(parsed, source)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(items)
}

// ── G-064: Discovery Graph Depth ─────────────────────────────────────────────

#[tauri::command]
fn get_related_artists(
    state: State<'_, AppState>,
    artist_name: String,
    limit: usize,
) -> Result<Vec<RelatedArtist>, String> {
    state
        .core
        .get_related_artists(artist_name, limit)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn play_similar_to_artist(
    app: AppHandle,
    state: State<'_, AppState>,
    artist_name: String,
    limit: usize,
) -> Result<Vec<QueueItemRecord>, String> {
    let queue = state
        .core
        .play_similar_to_artist(artist_name, limit)
        .map_err(|e| e.to_string())?;
    emit_queue(&app, &queue);
    Ok(queue)
}

#[tauri::command]
fn get_discovery_session(state: State<'_, AppState>) -> Result<DiscoverySession, String> {
    state
        .core
        .get_discovery_session()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn build_artist_graph(state: State<'_, AppState>) -> Result<usize, String> {
    state.core.build_artist_graph().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_graph_stats(state: State<'_, AppState>) -> Result<GraphStats, String> {
    state.core.get_graph_stats().map_err(|e| e.to_string())
}

// ─────────────────────────────────────────────────────────────────────────────

#[tauri::command]
fn create_playlist_from_queue(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
) -> Result<PlaylistDetail, String> {
    let payload = state
        .core
        .create_playlist_from_queue(name)
        .map_err(|e| e.to_string())?;
    emit_shell(&app, &state.core);
    Ok(payload)
}

fn main() {
    initialize_logging();

    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let app_data_dir = app.path().app_data_dir()?;
            fs::create_dir_all(&app_data_dir)?;
            let core = LyraCore::new(app_data_dir)
                .map_err(|error| tauri::Error::Anyhow(anyhow::anyhow!(error.to_string())))?;
            let state = AppState {
                core,
                sleep_until: Arc::new(std::sync::Mutex::new(None)),
            };
            restore_window_state(app.handle());
            create_tray(app.handle(), &state)?;
            register_shortcuts(app.handle(), &state);
            if let Ok(settings) = state.core.get_settings() {
                if settings.start_minimized {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
            }
            app.manage(state.clone());

            // Windows SMTC: register the bridge against the main window.
            #[cfg(target_os = "windows")]
            let smtc_bridge: Option<Arc<smtc::SmtcBridge>> = app
                .get_webview_window("main")
                .and_then(|w| smtc::SmtcBridge::new(&w, state.core.clone()))
                .map(Arc::new);
            #[cfg(not(target_os = "windows"))]
            let smtc_bridge: Option<()> = None;

            // Playback position ticker — emits state + handles auto-advance every second
            let core_tick = state.core.clone();
            let app_tick = app.handle().clone();
            let sleep_tick = state.sleep_until.clone();
            #[cfg(target_os = "windows")]
            let smtc_tick = smtc_bridge.clone();
            thread::spawn(move || {
                let mut tick: u32 = 0;
                loop {
                    thread::sleep(Duration::from_secs(1));
                    tick = tick.wrapping_add(1);
                    let Ok(playback) = core_tick.get_playback_state() else {
                        continue;
                    };
                    // Keep SMTC in sync with live playback state.
                    #[cfg(target_os = "windows")]
                    if let Some(smtc) = &smtc_tick {
                        smtc.update(&playback);
                    }
                    // Check sleep timer — stop if deadline has passed.
                    if playback.status == "playing" {
                        let expired = sleep_tick
                            .lock()
                            .map(|guard| {
                                guard
                                    .map(|t| std::time::Instant::now() >= t)
                                    .unwrap_or(false)
                            })
                            .unwrap_or(false);
                        if expired {
                            if let Ok(stopped) = core_tick.stop_playback() {
                                emit_playback(&app_tick, &stopped);
                            }
                            if let Ok(mut guard) = sleep_tick.lock() {
                                *guard = None;
                            }
                            let _ = app_tick.emit("lyra://sleep-timer-fired", ());
                            continue;
                        }
                    }
                    if playback.status == "playing" {
                        emit_playback(&app_tick, &playback);
                        // Persist live position every 5 ticks for accurate session restore.
                        if tick % 5 == 0 {
                            let _ = core_tick.sync_playback_state();
                        }
                        if core_tick.playback_finished() {
                            let queue_len = core_tick.get_queue().map(|q| q.len()).unwrap_or(0);
                            let next_idx = (playback.queue_index + 1) as usize;
                            // Record completion for the track that just finished
                            if let Some(track_id) = playback.current_track_id {
                                let duration = playback.duration_seconds.max(1.0);
                                let completion = (playback.position_seconds / duration).min(1.0);
                                let _ = core_tick.record_playback_event(
                                    track_id,
                                    completion,
                                    Some("player".to_string()),
                                );
                            }
                            if playback.repeat_mode == "one" {
                                // Repeat the current track.
                                if let Some(track_id) = playback.current_track_id {
                                    if let Ok(next) = core_tick.play_track(track_id) {
                                        emit_playback(&app_tick, &next);
                                    }
                                }
                            } else {
                                let should_advance =
                                    playback.repeat_mode == "all" || next_idx < queue_len;
                                if should_advance {
                                    if let Ok(next) = core_tick.play_next() {
                                        emit_playback(&app_tick, &next);
                                    }
                                } else {
                                    // Persist the stopped state so the ticker does not
                                    // fire this branch on every subsequent tick.
                                    if let Ok(stopped) = core_tick.stop_playback() {
                                        emit_playback(&app_tick, &stopped);
                                    }
                                }
                            }
                        }
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap_app,
            get_app_shell_state,
            list_tracks,
            get_library_overview,
            list_library_roots,
            add_library_root,
            remove_library_root,
            start_library_scan,
            get_scan_jobs,
            enrich_library,
            refresh_track_enrichment,
            validate_provider,
            keyring_save,
            keyring_load,
            keyring_delete,
            list_playlists,
            get_playlist_detail,
            create_playlist,
            rename_playlist,
            delete_playlist,
            add_track_to_playlist,
            remove_track_from_playlist,
            reorder_playlist_item,
            create_playlist_from_queue,
            enqueue_playlist,
            enqueue_tracks,
            get_queue,
            move_queue_item,
            remove_queue_item,
            clear_queue,
            get_playback_state,
            play_track,
            play_artist,
            play_album,
            play_queue_index,
            toggle_playback,
            stop_playback,
            list_audio_devices,
            set_output_device,
            enrich_track,
            play_next,
            play_previous,
            seek_to,
            set_volume,
            set_repeat_mode,
            set_shuffle,
            get_settings,
            update_settings,
            list_provider_configs,
            update_provider_config,
            run_legacy_import,
            get_native_capabilities,
            get_track_scores,
            get_taste_profile,
            get_recommendations,
            get_recommendation_bundle,
            explain_recommendation,
            enqueue_recommendation_leads,
            get_acquisition_queue,
            add_to_acquisition_queue,
            update_acquisition_item,
            process_acquisition_queue,
            clear_completed_acquisition,
            retry_failed_acquisition,
            set_acquisition_priority,
            move_acquisition_queue_item,
            set_acquisition_target_root,
            cancel_acquisition_item,
            acquisition_preflight,
            start_acquisition_worker,
            stop_acquisition_worker,
            acquisition_worker_status,
            run_diagnostics,
            list_playback_history,
            record_playback_event,
            get_track_detail,
            get_artist_profile,
            classify_track,
            classify_library,
            validate_track_text,
            prioritize_acquisition_queue,
            get_priority_batch,
            find_duplicates,
            list_provider_health,
            get_provider_health,
            record_provider_event,
            reset_provider_health,
            toggle_like,
            list_liked_tracks,
            lastfm_get_session,
            set_sleep_timer,
            get_sleep_timer,
            list_recent_plays,
            backup_env_to_keychain,
            load_env_credential,
            // G-061: Enrichment Provenance
            get_track_enrichment,
            // G-062: Curation Workflows
            resolve_duplicate_cluster,
            get_curation_log,
            undo_curation,
            preview_library_cleanup,
            // G-063: Playlist Intelligence
            compose_playlist_draft,
            compose_with_lyra,
            get_composer_diagnostics,
            get_recent_composer_runs,
            get_composer_run,
            get_spotify_gap_summary,
            save_composed_playlist,
            record_route_feedback,
            generate_act_playlist,
            save_generated_playlist,
            get_playlist_track_reasons,
            // Acquisition seeding
            seed_acquisition_from_spotify_library,
            bulk_add_to_acquisition_queue,
            // G-064: Discovery Graph Depth
            get_related_artists,
            play_similar_to_artist,
            get_discovery_session,
            build_artist_graph,
            get_graph_stats
        ])
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app, event| {
            if matches!(
                event,
                tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
            ) {
                persist_window_state(app);
            }
        });
}
