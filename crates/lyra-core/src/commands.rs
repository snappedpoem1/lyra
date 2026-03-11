use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

// Re-export diagnostics types
pub use crate::diagnostics::{ComponentHealth, DiagnosticsReport, SystemStats};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposerDiagnosticEntry {
    pub id: i64,
    pub level: String,
    pub event_type: String,
    pub prompt: String,
    pub action: Option<String>,
    pub provider: String,
    pub mode: String,
    pub message: String,
    pub payload_json: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposerRunRecord {
    pub id: i64,
    pub prompt: String,
    pub action: String,
    pub active_role: String,
    pub summary: String,
    pub provider: String,
    pub mode: String,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposerRunDetail {
    pub record: ComposerRunRecord,
    pub response: ComposerResponse,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpotifyTopArtist {
    pub artist: String,
    pub play_count: i64,
    pub total_ms_played: i64,
    pub owned_track_count: i64,
    pub missing_track_count: i64,
    pub last_played_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpotifyMissingCandidate {
    pub artist: String,
    pub title: String,
    pub album: Option<String>,
    pub spotify_uri: Option<String>,
    pub source: String,
    pub play_count: i64,
    pub last_played_at: Option<String>,
    pub already_queued: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpotifyGapSummary {
    pub available: bool,
    pub db_path: Option<String>,
    pub source_mode: String,
    pub legacy_import_observed: bool,
    pub last_legacy_import_at: Option<String>,
    pub last_legacy_imported_history: i64,
    pub last_legacy_imported_library: i64,
    pub last_legacy_imported_features: i64,
    pub history_count: i64,
    pub library_count: i64,
    pub features_count: i64,
    pub owned_overlap_count: i64,
    pub queued_overlap_count: i64,
    pub recoverable_missing_count: i64,
    pub top_artists: Vec<SpotifyTopArtist>,
    pub missing_candidates: Vec<SpotifyMissingCandidate>,
    pub summary_lines: Vec<String>,
}

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
#[serde(rename_all = "camelCase", default)]
pub struct SettingsPayload {
    pub start_minimized: bool,
    pub restore_session: bool,
    pub queue_panel_open: bool,
    pub playback_volume_step: i64,
    pub library_auto_scan: bool,
    pub preferred_output_device: Option<String>,
    pub composer_provider_preference: String,
    pub composer_default_track_count: i64,
    pub composer_explanation_depth: String,
    pub composer_taste_memory: Vec<String>,
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
            composer_provider_preference: "auto".to_string(),
            composer_default_track_count: 20,
            composer_explanation_depth: "balanced".to_string(),
            composer_taste_memory: Vec::new(),
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
pub struct AcquisitionPlanRecord {
    pub id: i64,
    pub kind: String,
    pub status: String,
    pub source: Option<String>,
    pub requested_artist: Option<String>,
    pub requested_title: Option<String>,
    pub requested_album: Option<String>,
    pub canonical_artist: Option<String>,
    pub canonical_album: Option<String>,
    pub summary: String,
    pub total_items: i64,
    pub queued_items: i64,
    pub blocked_items: i64,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionPlanItemRecord {
    pub id: i64,
    pub plan_id: i64,
    pub item_kind: String,
    pub status: String,
    pub artist: String,
    pub title: String,
    pub album: Option<String>,
    pub release_group_mbid: Option<String>,
    pub release_date: Option<String>,
    pub disc_number: Option<i64>,
    pub track_number: Option<i64>,
    pub queue_item_id: Option<i64>,
    pub evidence_level: String,
    pub evidence_summary: String,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionPlanResult {
    pub plan: AcquisitionPlanRecord,
    pub items: Vec<AcquisitionPlanItemRecord>,
    pub queue_items: Vec<AcquisitionQueueItem>,
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
    pub taste_memory: TasteMemorySnapshot,
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

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpotifyOauthSession {
    pub token_type: String,
    pub scopes: Vec<String>,
    pub access_token_expires_at: Option<String>,
    pub refreshed_at: String,
    pub has_refresh_token: bool,
    pub access_token_ready: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SpotifyOauthBootstrap {
    pub authorization_url: String,
    pub state: String,
    pub redirect_uri: String,
    pub scopes: Vec<String>,
    pub expires_at: String,
}

/// A track with a reason for its inclusion in a generated playlist.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistTrackWithReason {
    pub track: TrackRecord,
    pub reason: String,
    pub position: usize,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistIntentState {
    pub energy: String,
    pub descriptors: Vec<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistIntent {
    pub prompt: String,
    pub prompt_role: String,
    pub source_energy: String,
    pub destination_energy: String,
    pub opening_state: PlaylistIntentState,
    pub landing_state: PlaylistIntentState,
    pub transition_style: String,
    pub emotional_arc: Vec<String>,
    pub texture_descriptors: Vec<String>,
    pub explicit_entities: Vec<String>,
    pub familiarity_vs_novelty: String,
    pub discovery_aggressiveness: String,
    pub user_steer: Vec<String>,
    pub exclusions: Vec<String>,
    pub explanation_depth: String,
    pub sequencing_notes: Vec<String>,
    pub confidence_notes: Vec<String>,
    pub confidence: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposerProviderStatus {
    pub requested_provider: String,
    pub selected_provider: String,
    pub provider_kind: String,
    pub mode: String,
    pub fallback_reason: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistPhase {
    pub key: String,
    pub label: String,
    pub summary: String,
    pub target_energy: f64,
    pub target_valence: f64,
    pub target_tension: f64,
    pub target_warmth: f64,
    pub target_space: f64,
    pub novelty_bias: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TrackReasonPayload {
    pub summary: String,
    pub phase: String,
    pub why_this_track: String,
    pub transition_note: String,
    pub evidence: Vec<String>,
    pub explicit_from_prompt: Vec<String>,
    pub inferred_by_lyra: Vec<String>,
    pub confidence: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaylistTrackReasonRecord {
    pub track_id: i64,
    pub reason: String,
    pub reason_payload: Option<TrackReasonPayload>,
    pub phase_key: Option<String>,
    pub phase_label: Option<String>,
    pub position: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposedPlaylistTrack {
    pub track: TrackRecord,
    pub phase_key: String,
    pub phase_label: String,
    pub fit_score: f64,
    pub reason: TrackReasonPayload,
    pub position: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposedPlaylistDraft {
    pub name: String,
    pub prompt: String,
    pub intent: PlaylistIntent,
    pub provider_status: ComposerProviderStatus,
    pub phases: Vec<PlaylistPhase>,
    pub narrative: Option<String>,
    pub tracks: Vec<ComposedPlaylistTrack>,
}

/// The classified action type for a composer prompt.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ComposerAction {
    /// Standard playlist composition with phased arc.
    #[default]
    Playlist,
    /// Bridge path from source entity/vibe to destination entity/vibe.
    Bridge,
    /// Open-ended discovery / adjacency exploration.
    Discovery,
    /// Explain or interrogate existing choices.
    Explain,
    /// Steer/refine an existing draft (copilot mode).
    Steer,
}

/// A single step in a bridge path between two musical poles.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeStep {
    pub track: TrackRecord,
    pub fit_score: f64,
    pub role: String,
    pub why: String,
    pub distance_from_source: f64,
    pub distance_from_destination: f64,
    pub preserves: Vec<String>,
    pub changes: Vec<String>,
    pub adjacency_type: String,
    pub adjacency_signals: Vec<AdjacencySignal>,
    pub leads_to_next: String,
}

/// A bridge path result — an explained route between two musical poles.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgePath {
    pub source_label: String,
    pub destination_label: String,
    pub route_flavor: String,
    pub steps: Vec<BridgeStep>,
    pub narrative: Option<String>,
    pub confidence: f64,
    pub alternate_directions: Vec<String>,
    pub variants: Vec<RouteVariantSummary>,
}

/// A discovered adjacency with explanation.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoveryRoute {
    pub seed_label: String,
    pub primary_flavor: String,
    pub scene_exit: bool,
    pub directions: Vec<DiscoveryDirection>,
    pub narrative: Option<String>,
    pub confidence: f64,
    pub variants: Vec<RouteVariantSummary>,
}

/// One direction branch in a discovery result.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoveryDirection {
    pub flavor: String,
    pub label: String,
    pub description: String,
    pub tracks: Vec<ComposedPlaylistTrack>,
    pub why: String,
    pub preserves: Vec<String>,
    pub changes: Vec<String>,
    pub adjacency_signals: Vec<AdjacencySignal>,
    pub risk_note: String,
    pub reward_note: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AdjacencySignal {
    pub dimension: String,
    pub relation: String,
    pub score: f64,
    pub note: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RouteVariantSummary {
    pub flavor: String,
    pub label: String,
    pub logic: String,
    pub preserves: Vec<String>,
    pub changes: Vec<String>,
    pub risk_note: String,
    pub reward_note: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ResponsePosture {
    #[default]
    Suggestive,
    Refining,
    Collaborative,
    Revelatory,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DetailDepth {
    Short,
    #[default]
    Medium,
    Deep,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConfidenceVoice {
    pub level: String,
    pub phrasing: String,
    pub should_offer_alternatives: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FallbackVoice {
    pub active: bool,
    pub label: String,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RouteComparison {
    pub headline: String,
    pub summary: String,
    pub variants: Vec<RouteVariantSummary>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LyraReadSurface {
    pub summary: String,
    pub cues: Vec<String>,
    pub confidence_note: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LyraFraming {
    pub posture: ResponsePosture,
    pub detail_depth: DetailDepth,
    pub lead: String,
    pub rationale: String,
    pub presence_note: Option<String>,
    pub challenge: Option<String>,
    pub vibe_guard: Option<String>,
    pub confidence: ConfidenceVoice,
    pub fallback: FallbackVoice,
    pub route_comparison: Option<RouteComparison>,
    pub lyra_read: LyraReadSurface,
    pub sideways_temptations: Vec<String>,
    pub memory_hint: Option<String>,
    pub next_nudges: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RememberedPreference {
    pub axis_key: String,
    pub axis_label: String,
    pub preferred_pole: String,
    pub confidence: f64,
    pub evidence_count: i64,
    pub last_seen_at: String,
    pub recency_note: String,
    pub confidence_note: String,
    pub supporting_phrases: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RouteChoicePreference {
    pub route_kind: String,
    pub action: String,
    pub source: String,
    pub note: String,
    pub outcome: String,
    pub confidence: f64,
    pub observed_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RouteFeedbackPayload {
    pub route_kind: String,
    pub action: String,
    pub outcome: String,
    pub source: String,
    pub note: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionTastePosture {
    pub active_signals: Vec<String>,
    pub summary: String,
    pub confidence_note: String,
    pub updated_at: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TasteMemorySnapshot {
    pub session_posture: SessionTastePosture,
    pub remembered_preferences: Vec<RememberedPreference>,
    pub route_preferences: Vec<RouteChoicePreference>,
    pub summary_lines: Vec<String>,
}

/// Steering adjustments the user can apply post-composition.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SteerPayload {
    pub novelty_bias: Option<f64>,
    pub energy_bias: Option<f64>,
    pub warmth_bias: Option<f64>,
    pub adventurousness: Option<f64>,
    pub contrast_sharpness: Option<f64>,
    pub explanation_depth: Option<String>,
}

/// Unified composer response that wraps all possible intelligence outputs.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComposerResponse {
    pub action: ComposerAction,
    pub prompt: String,
    pub intent: PlaylistIntent,
    pub provider_status: ComposerProviderStatus,
    pub framing: LyraFraming,
    /// Present for Playlist and Steer actions.
    pub draft: Option<ComposedPlaylistDraft>,
    /// Present for Bridge actions.
    pub bridge: Option<BridgePath>,
    /// Present for Discovery actions.
    pub discovery: Option<DiscoveryRoute>,
    /// Present for Explain actions — free-form explanation text.
    pub explanation: Option<String>,
    /// Role that Lyra adopted for this response.
    pub active_role: String,
    /// Uncertainty notes Lyra wants to surface.
    pub uncertainty: Vec<String>,
    /// Alternatives Lyra considered but did not select.
    pub alternatives_considered: Vec<String>,
    /// Lightweight session-plus-rolling taste memory snapshot used in this response.
    pub taste_memory: TasteMemorySnapshot,
}

/// A playlist generated by the oracle from a user intent.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeneratedPlaylist {
    pub name: String,
    pub intent: String,
    /// LLM-generated liner notes narrative for the playlist journey.
    pub narrative: Option<String>,
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
    pub evidence_level: String,
    pub evidence_summary: String,
    pub why: String,
    pub preserves: Vec<String>,
    pub changes: Vec<String>,
    pub risk_note: String,
}

/// A flavored scout lane from a seed artist.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScoutExitLane {
    pub flavor: String, // safe | interesting | dangerous
    pub label: String,
    pub description: String,
    pub artists: Vec<RelatedArtist>,
}

/// Scout-style exits grouped into safe/interesting/dangerous lanes.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScoutExitPlan {
    pub seed_artist: String,
    pub lanes: Vec<ScoutExitLane>,
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

/// Artist node in the dimension-affinity graph.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GraphNode {
    pub artist: String,
    pub degree: usize,
}

/// Summary statistics for the artist graph.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GraphStats {
    pub total_artists: usize,
    pub total_connections: usize,
    pub top_connected: Vec<GraphNode>,
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

/// A single piece of scored evidence attached to a recommendation or explanation.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceItem {
    /// Machine-readable type tag: e.g. "taste_alignment", "scout_bridge", "co_play", "deep_cut"
    pub type_label: String,
    /// Which subsystem produced this signal: "local", "scout", "graph", "feedback"
    pub source: String,
    /// Evidence bucket used for honest explainability rollups.
    pub category: String,
    /// Concrete anchor for where the evidence came from.
    pub anchor: String,
    /// Human-readable explanation sentence.
    pub text: String,
    /// Relative weight of this signal in the final score (0.0–1.0).
    pub weight: f64,
}

/// Human-readable explanation of why a track was recommended.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExplainPayload {
    pub track_id: i64,
    /// Short single-sentence "why" at composer payload depth.
    pub why_this_track: String,
    /// Overall evidence posture for this explanation.
    pub evidence_grade: String,
    /// Legacy flat reasons list (kept for backward compat).
    pub reasons: Vec<String>,
    /// Structured evidence items mirroring TrackReasonPayload depth.
    pub evidence_items: Vec<EvidenceItem>,
    /// Facts pulled directly from the prompt or explicit library evidence.
    pub explicit_from_prompt: Vec<String>,
    /// Signals inferred by Lyra from taste/graph/scout rather than stated explicitly.
    pub inferred_by_lyra: Vec<String>,
    pub confidence: f64,
    pub source: String,
}

/// A recommended track with broker-grade evidence.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecommendationResult {
    pub track: TrackRecord,
    pub score: f64,
    /// Which broker lane produced this candidate: "local", "scout", "graph"
    pub provider: String,
    /// Single-sentence reason at composer payload depth.
    pub why_this_track: String,
    /// Overall evidence posture for this candidate.
    pub evidence_grade: String,
    /// Structured evidence items.
    pub evidence: Vec<EvidenceItem>,
}

/// Non-local recommendation output that can be handed off into acquisition.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionLead {
    pub artist: String,
    pub title: String,
    pub provider: String,
    pub score: f64,
    pub reason: String,
    pub evidence_grade: String,
    pub evidence: Vec<EvidenceItem>,
}

/// Broker output including both owned-library recommendations and acquisition leads.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecommendationBundle {
    pub recommendations: Vec<RecommendationResult>,
    pub acquisition_leads: Vec<AcquisitionLead>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionLeadOutcome {
    pub artist: String,
    pub title: String,
    pub provider: String,
    pub status: String, // queued | duplicate_active | error
    pub detail: String,
    pub queue_item_id: Option<i64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionLeadHandoffReport {
    pub outcomes: Vec<AcquisitionLeadOutcome>,
    pub queued_count: i64,
    pub duplicate_count: i64,
    pub error_count: i64,
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

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LastfmSyncResult {
    pub fetched: usize,
    pub matched: usize,
    pub written: usize,
}
