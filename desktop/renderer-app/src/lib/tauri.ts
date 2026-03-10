import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  AcquisitionLeadHandoffReport,
  AcquisitionQueueItem,
  AcquisitionPreflight,
  AppShellState,
  AudioOutputDevice,
  BootstrapPayload,
  ComposerResponse,
  ComposerDiagnosticEntry,
  ComposerRunDetail,
  ComposerRunRecord,
  ComposedPlaylistDraft,
  CurationLogEntry,
  DiagnosticsReport,
  DiscoverySession,
  DuplicateCluster,
  GraphStats,
  ExplainPayload,
  GeneratedPlaylist,
  LegacyImportReport,
  LibraryCleanupPreview,
  LibraryOverview,
  LibraryRootRecord,
  PlaybackEvent,
  PlaybackState,
  PlaylistDetail,
  PlaylistTrackReasonRecord,
  PlaylistSummary,
  ProviderConfigRecord,
  ProviderHealth,
  ProviderValidationResult,
  QueueItemRecord,
  RecentPlayRecord,
  RecommendationBundle,
  RecommendationResult,
  AcquisitionLead,
  RelatedArtist,
  ScoutExitPlan,
  ScoutTarget,
  BridgeArtist,
  MoodSearchResult,
  DeepCutTrack,
  ScanJobRecord,
  SearchSemanticCapability,
  SettingsPayload,
  SpotifyGapSummary,
  SteerPayload,
  TasteProfile,
  ArtistProfile,
  TrackDetail,
  TrackEnrichmentResult,
  TrackRecord,
  TrackScores
} from "$lib/types";

export const api = {
  bootstrap: () => invoke<BootstrapPayload>("bootstrap_app"),
  shell: () => invoke<AppShellState>("get_app_shell_state"),
  tracks: (query?: string, sort?: string) => invoke<TrackRecord[]>("list_tracks", { query, sort }),
  libraryOverview: () => invoke<LibraryOverview>("get_library_overview"),
  libraryRoots: () => invoke<LibraryRootRecord[]>("list_library_roots"),
  addLibraryRoot: (path: string) => invoke<LibraryRootRecord[]>("add_library_root", { path }),
  removeLibraryRoot: (rootId: number) => invoke<LibraryRootRecord[]>("remove_library_root", { rootId }),
  startScan: () => invoke<ScanJobRecord>("start_library_scan"),
  scanJobs: () => invoke<ScanJobRecord[]>("get_scan_jobs"),
  playlists: () => invoke<PlaylistSummary[]>("list_playlists"),
  playlistDetail: (playlistId: number) => invoke<PlaylistDetail>("get_playlist_detail", { playlistId }),
  createPlaylist: (name: string) => invoke<PlaylistDetail>("create_playlist", { name }),
  renamePlaylist: (playlistId: number, name: string) => invoke<PlaylistDetail>("rename_playlist", { playlistId, name }),
  deletePlaylist: (playlistId: number) => invoke<PlaylistSummary[]>("delete_playlist", { playlistId }),
  addTrackToPlaylist: (playlistId: number, trackId: number) => invoke<PlaylistDetail>("add_track_to_playlist", { playlistId, trackId }),
  removeTrackFromPlaylist: (playlistId: number, trackId: number) => invoke<PlaylistDetail>("remove_track_from_playlist", { playlistId, trackId }),
  reorderPlaylistItem: (playlistId: number, trackId: number, newPosition: number) => invoke<PlaylistDetail>("reorder_playlist_item", { playlistId, trackId, newPosition }),
  createPlaylistFromQueue: (name: string) => invoke<PlaylistDetail>("create_playlist_from_queue", { name }),
  enqueuePlaylist: (playlistId: number) => invoke<QueueItemRecord[]>("enqueue_playlist", { playlistId }),
  enqueueTracks: (trackIds: number[]) => invoke<QueueItemRecord[]>("enqueue_tracks", { trackIds }),
  queue: () => invoke<QueueItemRecord[]>("get_queue"),
  moveQueueItem: (queueItemId: number, newPosition: number) => invoke<QueueItemRecord[]>("move_queue_item", { queueItemId, newPosition }),
  removeQueueItem: (queueItemId: number) => invoke<QueueItemRecord[]>("remove_queue_item", { queueItemId }),
  clearQueue: () => invoke<QueueItemRecord[]>("clear_queue"),
  playback: () => invoke<PlaybackState>("get_playback_state"),
  playTrack: (trackId: number) => invoke<PlaybackState>("play_track", { trackId }),
  playArtist: (artistName: string) => invoke<PlaybackState>("play_artist", { artistName }),
  playAlbum: (artistName: string, albumTitle: string) =>
    invoke<PlaybackState>("play_album", { artistName, albumTitle }),
  playQueueIndex: (index: number) => invoke<PlaybackState>("play_queue_index", { index }),
  togglePlayback: () => invoke<PlaybackState>("toggle_playback"),
  playNext: () => invoke<PlaybackState>("play_next"),
  playPrevious: () => invoke<PlaybackState>("play_previous"),
  seekTo: (positionSeconds: number) => invoke<PlaybackState>("seek_to", { positionSeconds }),
  setVolume: (volume: number) => invoke<PlaybackState>("set_volume", { volume }),
  setRepeatMode: (repeatMode: string) => invoke<PlaybackState>("set_repeat_mode", { repeatMode }),
  setShuffle: (shuffle: boolean) => invoke<PlaybackState>("set_shuffle", { shuffle }),
  settings: () => invoke<SettingsPayload>("get_settings"),
  updateSettings: (settings: SettingsPayload) => invoke<SettingsPayload>("update_settings", { settings }),
  listAudioDevices: () => invoke<AudioOutputDevice[]>("list_audio_devices"),
  setOutputDevice: (deviceName: string | null) => invoke<void>("set_output_device", { deviceName }),
  providerConfigs: () => invoke<ProviderConfigRecord[]>("list_provider_configs"),
  updateProviderConfig: (providerKey: string, enabled: boolean, values: Record<string, unknown>) =>
    invoke<ProviderConfigRecord[]>("update_provider_config", { payload: { providerKey, enabled, values } }),
  legacyImport: (envPath?: string, legacyDbPath?: string) =>
    invoke<LegacyImportReport>("run_legacy_import", { payload: { envPath, legacyDbPath } }),
  // --- scores / taste / acquisition / history ---
  trackScores: (trackId: number) => invoke<TrackScores | null>("get_track_scores", { trackId }),
  tasteProfile: () => invoke<TasteProfile>("get_taste_profile"),
  acquisitionQueue: (statusFilter?: string) =>
    invoke<AcquisitionQueueItem[]>("get_acquisition_queue", { statusFilter }),
  addToAcquisitionQueue: (artist: string, title: string, album?: string, source?: string, targetRootId?: number) =>
    invoke<AcquisitionQueueItem[]>("add_to_acquisition_queue", { artist, title, album, source, targetRootId }),
  updateAcquisitionItem: (id: number, status: string, error?: string) =>
    invoke<AcquisitionQueueItem[]>("update_acquisition_item", { id, status, error }),
  processAcquisitionQueue: () =>
    invoke<boolean>("process_acquisition_queue"),
  clearCompletedAcquisition: () =>
    invoke<number>("clear_completed_acquisition"),
  retryFailedAcquisition: () =>
    invoke<number>("retry_failed_acquisition"),
  setAcquisitionPriority: (id: number, priorityScore: number) =>
    invoke<AcquisitionQueueItem[]>("set_acquisition_priority", { id, priorityScore }),
  moveAcquisitionQueueItem: (id: number, newPosition: number) =>
    invoke<AcquisitionQueueItem[]>("move_acquisition_queue_item", { id, newPosition }),
  setAcquisitionTargetRoot: (id: number, targetRootId?: number) =>
    invoke<AcquisitionQueueItem[]>("set_acquisition_target_root", { id, targetRootId }),
  cancelAcquisitionItem: (id: number, detail?: string) =>
    invoke<AcquisitionQueueItem[]>("cancel_acquisition_item", { id, detail }),
  acquisitionPreflight: () =>
    invoke<AcquisitionPreflight>("acquisition_preflight"),
  startAcquisitionWorker: () =>
    invoke<boolean>("start_acquisition_worker"),
  stopAcquisitionWorker: () =>
    invoke<void>("stop_acquisition_worker"),
  acquisitionWorkerStatus: () =>
    invoke<boolean>("acquisition_worker_status"),
  runDiagnostics: () =>
    invoke<DiagnosticsReport>("run_diagnostics"),
  playbackHistory: (limit?: number) => invoke<PlaybackEvent[]>("list_playback_history", { limit }),
  recordPlaybackEvent: (trackId: number, completionRate: number, context?: string) =>
    invoke<void>("record_playback_event", { trackId, completionRate, context }),
  trackDetail: (trackId: number) => invoke<TrackDetail | null>("get_track_detail", { trackId }),
  getArtistProfile: (artistName: string) => invoke<ArtistProfile | null>("get_artist_profile", { artistName }),
  // --- duplicates + provider health ---
  findDuplicates: () => invoke<DuplicateCluster[]>("find_duplicates"),
  listProviderHealth: () => invoke<ProviderHealth[]>("list_provider_health"),
  getProviderHealth: (providerKey: string) =>
    invoke<ProviderHealth>("get_provider_health", { providerKey }),
  recordProviderEvent: (providerKey: string, success: boolean) =>
    invoke<ProviderHealth>("record_provider_event", { providerKey, success }),
  resetProviderHealth: (providerKey: string) =>
    invoke<ProviderHealth[]>("reset_provider_health", { providerKey }),
  // --- enrichment ---
  enrichTrack: (trackId: number) => invoke<Record<string, unknown>>("enrich_track", { trackId }),
  enrichLibrary: () => invoke<void>("enrich_library"),
  refreshTrackEnrichment: (trackId: number) =>
    invoke<Record<string, unknown>>("refresh_track_enrichment", { trackId }),
  validateProvider: (providerKey: string) =>
    invoke<ProviderValidationResult>("validate_provider", { providerKey }),
  // --- recommendations / oracle ---
  getRecommendations: (limit?: number) =>
    invoke<RecommendationResult[]>("get_recommendations", { limit }),
  getRecommendationBundle: (limit?: number) =>
    invoke<RecommendationBundle>("get_recommendation_bundle", { limit }),
  explainRecommendation: (trackId: number) =>
    invoke<ExplainPayload>("explain_recommendation", { trackId }),
  enqueueRecommendationLeads: (leads: AcquisitionLead[]) =>
    invoke<AcquisitionLeadHandoffReport>("enqueue_recommendation_leads", { leads }),
  // --- keyring / secure credentials ---
  keyringSave: (providerKey: string, keyName: string, secret: string) =>
    invoke<void>("keyring_save", { providerKey, keyName, secret }),
  keyringLoad: (providerKey: string, keyName: string) =>
    invoke<string | null>("keyring_load", { providerKey, keyName }),
  keyringDelete: (providerKey: string, keyName: string) =>
    invoke<void>("keyring_delete", { providerKey, keyName }),
  // --- liked tracks ---
  toggleLike: (trackId: number) => invoke<boolean>("toggle_like", { trackId }),
  listLikedTracks: () => invoke<TrackRecord[]>("list_liked_tracks"),
  // --- Last.fm auth ---
  lastfmGetSession: (apiKey: string, apiSecret: string, username: string, password: string) =>
    invoke<string>("lastfm_get_session", { apiKey, apiSecret, username, password }),
  // --- sleep timer ---
  setSleepTimer: (minutes: number) => invoke<void>("set_sleep_timer", { minutes }),
  getSleepTimer: () => invoke<number | null>("get_sleep_timer"),
  // --- recent plays ---
  listRecentPlays: (limit?: number) => invoke<RecentPlayRecord[]>("list_recent_plays", { limit }),
  // --- env keychain backup ---
  backupEnvToKeychain: (envPath: string) => invoke<{ saved: number; skipped: number }>("backup_env_to_keychain", { envPath }),
  loadEnvCredential: (keyName: string) => invoke<string | null>("load_env_credential", { keyName }),
  // --- G-061: Enrichment Provenance ---
  getTrackEnrichment: (trackId: number) => invoke<TrackEnrichmentResult>("get_track_enrichment", { trackId }),
  // --- G-062: Curation Workflows ---
  resolveDuplicateCluster: (keepTrackId: number, removeTrackIds: number[]) =>
    invoke<void>("resolve_duplicate_cluster", { keepTrackId, removeTrackIds }),
  getCurationLog: () => invoke<CurationLogEntry[]>("get_curation_log"),
  undoCuration: (logId: number) => invoke<void>("undo_curation", { logId }),
  previewLibraryCleanup: () => invoke<LibraryCleanupPreview>("preview_library_cleanup"),
  // --- G-063: Playlist Intelligence ---
  composePlaylistDraft: (prompt: string, trackCount: number) =>
    invoke<ComposedPlaylistDraft>("compose_playlist_draft", { prompt, trackCount }),
  composeWithLyra: (prompt: string, trackCount: number, steer?: SteerPayload) =>
    invoke<ComposerResponse>("compose_with_lyra", { prompt, trackCount, steer }),
  getComposerDiagnostics: (limit?: number) =>
    invoke<ComposerDiagnosticEntry[]>("get_composer_diagnostics", { limit }),
  getRecentComposerRuns: (limit?: number) =>
    invoke<ComposerRunRecord[]>("get_recent_composer_runs", { limit }),
  getComposerRun: (runId: number) =>
    invoke<ComposerRunDetail>("get_composer_run", { runId }),
  getSpotifyGapSummary: (limit?: number) =>
    invoke<SpotifyGapSummary>("get_spotify_gap_summary", { limit }),
  saveComposedPlaylist: (name: string, draft: ComposedPlaylistDraft) =>
    invoke<PlaylistDetail>("save_composed_playlist", { name, draft }),
  recordRouteFeedback: (
    routeKind: string,
    action: string,
    outcome: string,
    source: string,
    note?: string
  ) => invoke<AppShellState["tasteMemory"]>("record_route_feedback", {
    payload: { routeKind, action, outcome, source, note }
  }),
  generateActPlaylist: (intent: string, trackCount: number) =>
    invoke<GeneratedPlaylist>("generate_act_playlist", { intent, trackCount }),
  saveGeneratedPlaylist: (name: string, playlist: GeneratedPlaylist) =>
    invoke<PlaylistDetail>("save_generated_playlist", { name, playlist }),
  getPlaylistTrackReasons: (playlistId: number) =>
    invoke<PlaylistTrackReasonRecord[]>("get_playlist_track_reasons", { playlistId }),
  // --- Acquisition Seeding ---
  seedAcquisitionFromSpotifyLibrary: () =>
    invoke<number>("seed_acquisition_from_spotify_library"),
  bulkAddToAcquisitionQueue: (
    entries: [string, string, string | null][],
    source: string,
  ) => invoke<AcquisitionQueueItem[]>("bulk_add_to_acquisition_queue", { entries, source }),
  // --- G-064: Discovery Graph Depth ---
  getRelatedArtists: (artistName: string, limit: number) =>
    invoke<RelatedArtist[]>("get_related_artists", { artistName, limit }),
  getScoutExitPlan: (artistName: string, limitPerLane?: number) =>
    invoke<ScoutExitPlan>("get_scout_exit_plan", { artistName, limitPerLane }),
  crossGenreHunt: (genreA: string, genreB: string, limit: number) =>
    invoke<ScoutTarget[]>("cross_genre_hunt", { genreA, genreB, limit }),
  findLocalBridgeArtists: (genreA: string, genreB: string) =>
    invoke<BridgeArtist[]>("find_local_bridge_artists", { genreA, genreB }),
  discoverByMood: (mood: string, limit: number) =>
    invoke<MoodSearchResult[]>("discover_by_mood", { mood, limit }),
  deepcutHunt: (genre: string | null, artist: string | null, minObscurity: number, limit: number) =>
    invoke<DeepCutTrack[]>("deepcut_hunt", { genre, artist, minObscurity, limit }),
  playSimilarToArtist: (artistName: string, limit: number) =>
    invoke<QueueItemRecord[]>("play_similar_to_artist", { artistName, limit }),
  getDiscoverySession: () => invoke<DiscoverySession>("get_discovery_session"),
  buildArtistGraph: () => invoke<number>("build_artist_graph"),
  getGraphStats: () => invoke<GraphStats>("get_graph_stats"),
  getSemanticSearchCapability: () =>
    invoke<SearchSemanticCapability>("get_semantic_search_capability"),
  on<T>(event: string, callback: (payload: T) => void) {
    return listen<T>(event, (message) => callback(message.payload));
  }
};
