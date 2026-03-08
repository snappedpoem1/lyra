import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  AcquisitionQueueItem,
  AppShellState,
  AudioOutputDevice,
  BootstrapPayload,
  DuplicateCluster,
  LegacyImportReport,
  LibraryOverview,
  LibraryRootRecord,
  PlaybackEvent,
  PlaybackState,
  PlaylistDetail,
  PlaylistSummary,
  ProviderConfigRecord,
  ProviderHealth,
  QueueItemRecord,
  ScanJobRecord,
  SettingsPayload,
  TasteProfile,
  TrackDetail,
  TrackRecord,
  TrackScores
} from "$lib/types";

export const api = {
  bootstrap: () => invoke<BootstrapPayload>("bootstrap_app"),
  shell: () => invoke<AppShellState>("get_app_shell_state"),
  tracks: (query?: string) => invoke<TrackRecord[]>("list_tracks", { query }),
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
  addToAcquisitionQueue: (artist: string, title: string, album?: string, source?: string) =>
    invoke<AcquisitionQueueItem[]>("add_to_acquisition_queue", { artist, title, album, source }),
  updateAcquisitionItem: (id: number, status: string, error?: string) =>
    invoke<AcquisitionQueueItem[]>("update_acquisition_item", { id, status, error }),
  playbackHistory: (limit?: number) => invoke<PlaybackEvent[]>("list_playback_history", { limit }),
  recordPlaybackEvent: (trackId: number, completionRate: number, context?: string) =>
    invoke<void>("record_playback_event", { trackId, completionRate, context }),
  trackDetail: (trackId: number) => invoke<TrackDetail | null>("get_track_detail", { trackId }),
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
  on<T>(event: string, callback: (payload: T) => void) {
    return listen<T>(event, (message) => callback(message.payload));
  }
};

