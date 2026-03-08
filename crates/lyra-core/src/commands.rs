use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

// Re-export diagnostics types
pub use crate::diagnostics::{ComponentHealth, DiagnosticsReport, SystemStats};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioOutputDevice {
    pub id: String,
    pub name: String,
    pub is_default: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TrackRecord {
    pub id: i64,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub path: String,
    pub duration_seconds: f64,
    pub genre: Option<String>,
    pub year: Option<String>,
    pub bpm: Option<f64>,
    pub key_signature: Option<String>,
    pub liked: bool,
    pub liked_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryOverview {
    pub track_count: i64,
    pub album_count: i64,
    pub artist_count: i64,
    pub root_count: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryRootRecord {
    pub id: i64,
    pub path: String,
    pub added_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScanJobRecord {
    pub id: i64,
    pub status: String,
    pub files_scanned: i64,
    pub tracks_imported: i64,
    pub started_at: String,
    pub finished_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistSummary {
    pub id: i64,
    pub name: String,
    pub description: String,
    pub item_count: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistDetail {
    pub id: i64,
    pub name: String,
    pub description: String,
    pub items: Vec<TrackRecord>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct QueueItemRecord {
    pub id: i64,
    pub position: i64,
    pub track_id: i64,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub path: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaybackState {
    pub status: String,
    pub current_track_id: Option<i64>,
    pub current_track: Option<TrackRecord>,
    pub queue_index: i64,
    pub position_seconds: f64,
    pub duration_seconds: f64,
    pub volume: f64,
    pub shuffle: bool,
    pub repeat_mode: String,
    pub seek_supported: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsPayload {
    pub start_minimized: bool,
    pub restore_session: bool,
    pub queue_panel_open: bool,
    pub playback_volume_step: i64,
    pub library_auto_scan: bool,
    pub preferred_output_device: Option<String>,
}

impl Default for SettingsPayload {
    fn default() -> Self {
        Self {
            start_minimized: false,
            restore_session: true,
            queue_panel_open: true,
            playback_volume_step: 5,
            library_auto_scan: false,
            preferred_output_device: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderConfigRecord {
    pub provider_key: String,
    pub display_name: String,
    pub enabled: bool,
    pub is_configured: bool,
    pub config: Value,
    pub capabilities: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LegacyImportReport {
    pub imported: Vec<String>,
    pub unsupported: Vec<String>,
    pub notes: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TrackScores {
    pub track_id: i64,
    pub energy: f64,
    pub valence: f64,
    pub tension: f64,
    pub density: f64,
    pub warmth: f64,
    pub movement: f64,
    pub space: f64,
    pub rawness: f64,
    pub complexity: f64,
    pub nostalgia: f64,
    pub bpm: Option<f64>,
    pub key_signature: Option<String>,
    pub scored_at: String,
    pub score_version: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TasteProfile {
    pub dimensions: HashMap<String, f64>,
    pub confidence: f64,
    pub total_signals: i64,
    pub source: String,
}

impl Default for TasteProfile {
    fn default() -> Self {
        Self {
            dimensions: HashMap::new(),
            confidence: 0.0,
            total_signals: 0,
            source: "none".to_string(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionQueueItem {
    pub id: i64,
    pub artist: String,
    pub title: String,
    pub album: Option<String>,
    pub status: String,
    pub priority_score: f64,
    pub source: Option<String>,
    pub added_at: String,
    pub completed_at: Option<String>,
    pub error: Option<String>,
    pub retry_count: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaybackEvent {
    pub id: i64,
    pub track_id: i64,
    pub ts: String,
    pub context: Option<String>,
    pub completion_rate: Option<f64>,
    pub skipped: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecentPlayRecord {
    pub id: i64,
    pub track_id: i64,
    pub artist: String,
    pub title: String,
    pub ts: String,
    pub completion_rate: Option<f64>,
    pub skipped: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TrackDetail {
    pub track: TrackRecord,
    pub scores: Option<TrackScores>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DuplicateCluster {
    pub tracks: Vec<TrackRecord>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderHealth {
    pub provider_key: String,
    pub status: String,
    pub failure_count: i64,
    pub last_failure: Option<String>,
    pub last_success: Option<String>,
    pub circuit_open: bool,
    pub last_check: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeCapabilities {
    pub tray_supported: bool,
    pub menu_supported: bool,
    pub global_shortcuts_supported: bool,
    pub seek_supported: bool,
    pub media_controls_hooked: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppShellState {
    pub library_overview: LibraryOverview,
    pub library_roots: Vec<LibraryRootRecord>,
    pub playlists: Vec<PlaylistSummary>,
    pub queue: Vec<QueueItemRecord>,
    pub playback: PlaybackState,
    pub settings: SettingsPayload,
    pub providers: Vec<ProviderConfigRecord>,
    pub scan_jobs: Vec<ScanJobRecord>,
    pub taste_profile: TasteProfile,
    pub acquisition_queue_pending: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BootstrapPayload {
    pub shell: AppShellState,
    pub native_capabilities: NativeCapabilities,
}

/// Result of a lightweight provider credential validation probe.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderValidationResult {
    pub provider_key: String,
    pub valid: bool,
    pub latency_ms: u64,
    pub error: Option<String>,
    pub detail: Option<String>,
}

/// Human-readable explanation of why a track was recommended.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExplainPayload {
    pub track_id: i64,
    pub reasons: Vec<String>,
    pub confidence: f64,
    pub source: String,
}

/// A recommended track with its similarity score.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecommendationResult {
    pub track: TrackRecord,
    pub score: f64,
}
