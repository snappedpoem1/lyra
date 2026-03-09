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
    pub queue_position: i64,
    pub priority_score: f64,
    pub source: Option<String>,
    pub added_at: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub failed_at: Option<String>,
    pub cancelled_at: Option<String>,
    pub error: Option<String>,
    pub status_message: Option<String>,
    pub failure_stage: Option<String>,
    pub failure_reason: Option<String>,
    pub failure_detail: Option<String>,
    pub retry_count: i64,
    pub selected_provider: Option<String>,
    pub selected_tier: Option<String>,
    pub worker_label: Option<String>,
    pub validation_confidence: Option<f64>,
    pub validation_summary: Option<String>,
    pub target_root_id: Option<i64>,
    pub target_root_path: Option<String>,
    pub output_path: Option<String>,
    pub downstream_track_id: Option<i64>,
    pub scan_completed: bool,
    pub organize_completed: bool,
    pub index_completed: bool,
    pub cancel_requested: bool,
    pub lifecycle_stage: Option<String>,
    pub lifecycle_progress: Option<f64>,
    pub lifecycle_note: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionPreflightCheck {
    pub key: String,
    pub label: String,
    pub status: String,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionPreflight {
    pub ready: bool,
    pub python_available: bool,
    pub downloader_available: bool,
    pub disk_ok: bool,
    pub library_root_ok: bool,
    pub output_path_ok: bool,
    pub free_bytes: i64,
    pub required_bytes: i64,
    pub checks: Vec<AcquisitionPreflightCheck>,
    pub notes: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionEventPayload {
    pub queue: Vec<AcquisitionQueueItem>,
    pub worker_running: bool,
    pub latest_item_id: Option<i64>,
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

/// A track with a reason for its inclusion in a generated playlist.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistTrackWithReason {
    pub track: TrackRecord,
    pub reason: String,
    pub position: usize,
}

/// A playlist generated by the oracle from a user intent.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeneratedPlaylist {
    pub name: String,
    pub intent: String,
    pub tracks: Vec<PlaylistTrackWithReason>,
}

/// Related artist with connection metadata.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RelatedArtist {
    pub name: String,
    pub connection_strength: f32,
    pub connection_type: String, // "similar", "collab", "genre"
    pub local_track_count: usize,
}

/// A single discovery interaction in the session.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoveryInteraction {
    pub artist_name: String,
    pub action: String,
    pub created_at: String,
}

/// Recent discovery session history.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoverySession {
    pub recent: Vec<DiscoveryInteraction>,
}

/// Per-provider enrichment entry with source/confidence metadata.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EnrichmentEntry {
    pub provider: String,
    pub status: String,
    pub confidence: f32,
    pub note: Option<String>,
    pub mbid: Option<String>,
    pub release_mbid: Option<String>,
    pub release_title: Option<String>,
    pub release_date: Option<String>,
    pub match_score: Option<f32>,
    pub listeners: Option<i64>,
    pub play_count: Option<i64>,
    pub tags: Vec<String>,
    pub wiki_summary: Option<String>,
    pub year: Option<i32>,
    pub genres: Vec<String>,
    pub label: Option<String>,
    pub lyrics_url: Option<String>,
    pub has_lrc: Option<bool>,
}

/// Curation log entry for undo display.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CurationLogEntry {
    pub log_id: i64,
    pub action: String, // "resolve_duplicate", "quarantine", "rename"
    pub track_ids: Vec<i64>,
    pub detail: String,
    pub created_at: String,
    pub undone: bool,
}

/// A single cleanup issue found during preview.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CleanupIssue {
    pub issue_type: String, // "missing_artist", "missing_album", "inconsistent_case", "suspected_duplicate"
    pub track_id: i64,
    pub current_value: String,
    pub suggested_value: String,
    pub severity: String, // "high", "medium", "low"
}

/// Preview result for library cleanup.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryCleanupPreview {
    pub issues: Vec<CleanupIssue>,
}

/// Full enrichment result for a track, grouped by provider.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TrackEnrichmentResult {
    pub track_id: i64,
    pub enrichment_state: String, // "not_enriched", "enriching", "enriched", "failed"
    pub entries: Vec<EnrichmentEntry>,
    pub primary_mbid: Option<String>, // best recording MBID across all providers
    pub identity_confidence: f32,
    pub degraded_providers: Vec<String>,
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

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtistConnection {
    pub artist: String,
    pub score: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtistProfile {
    pub artist: String,
    pub track_count: i64,
    pub album_count: i64,
    pub albums: Vec<String>,
    pub genres: Vec<String>,
    pub bio: Option<String>,
    pub image_url: Option<String>,
    pub lastfm_url: Option<String>,
    pub primary_mbid: Option<String>,
    pub identity_confidence: f32,
    pub provenance: Vec<EnrichmentEntry>,
    pub top_tracks: Vec<TrackRecord>,
    pub connections: Vec<ArtistConnection>,
}
