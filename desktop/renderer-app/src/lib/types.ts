export type TrackRecord = {
  id: number;
  title: string;
  artist: string;
  album: string;
  path: string;
  durationSeconds: number;
  genre?: string | null;
  year?: string | null;
  bpm?: number | null;
  keySignature?: string | null;
  liked: boolean;
  likedAt?: string | null;
};

export type LibraryOverview = {
  trackCount: number;
  albumCount: number;
  artistCount: number;
  rootCount: number;
};

export type LibraryRootRecord = {
  id: number;
  path: string;
  addedAt: string;
};

export type ScanJobRecord = {
  id: number;
  status: string;
  filesScanned: number;
  tracksImported: number;
  startedAt: string;
  finishedAt?: string | null;
};

export type PlaylistSummary = {
  id: number;
  name: string;
  description: string;
  itemCount: number;
};

export type PlaylistDetail = {
  id: number;
  name: string;
  description: string;
  items: TrackRecord[];
};

export type QueueItemRecord = {
  id: number;
  position: number;
  trackId: number;
  title: string;
  artist: string;
  album: string;
  path: string;
};

export type PlaybackState = {
  status: string;
  currentTrackId?: number | null;
  currentTrack?: TrackRecord | null;
  queueIndex: number;
  positionSeconds: number;
  durationSeconds: number;
  volume: number;
  shuffle: boolean;
  repeatMode: string;
  seekSupported: boolean;
};

export type AudioOutputDevice = {
  id: string;
  name: string;
  isDefault: boolean;
};

export type SettingsPayload = {
  startMinimized: boolean;
  restoreSession: boolean;
  queuePanelOpen: boolean;
  playbackVolumeStep: number;
  libraryAutoScan: boolean;
  preferredOutputDevice: string | null;
};

export type ProviderConfigRecord = {
  providerKey: string;
  displayName: string;
  enabled: boolean;
  isConfigured: boolean;
  config: Record<string, unknown>;
  capabilities: string[];
};

export type AppShellState = {
  libraryOverview: LibraryOverview;
  libraryRoots: LibraryRootRecord[];
  playlists: PlaylistSummary[];
  queue: QueueItemRecord[];
  playback: PlaybackState;
  settings: SettingsPayload;
  providers: ProviderConfigRecord[];
  scanJobs: ScanJobRecord[];
  tasteProfile: TasteProfile;
  acquisitionQueuePending: number;
};

export type BootstrapPayload = {
  shell: AppShellState;
  nativeCapabilities: {
    traySupported: boolean;
    menuSupported: boolean;
    globalShortcutsSupported: boolean;
    seekSupported: boolean;
    mediaControlsHooked: boolean;
  };
};

export type LegacyImportReport = {
  imported: string[];
  unsupported: string[];
  notes: string[];
};

export type TrackScores = {
  trackId: number;
  energy: number;
  valence: number;
  tension: number;
  density: number;
  warmth: number;
  movement: number;
  space: number;
  rawness: number;
  complexity: number;
  nostalgia: number;
  bpm?: number | null;
  keySignature?: string | null;
  scoredAt?: string | null;
  scoreVersion?: number | null;
};

export type TasteProfile = {
  dimensions: Record<string, number>;
  confidence: number;
  totalSignals: number;
  source: string;
};

export type AcquisitionQueueItem = {
  id: number;
  artist: string;
  title: string;
  album?: string | null;
  status: string;
  priorityScore: number;
  source?: string | null;
  addedAt: string;
  completedAt?: string | null;
  error?: string | null;
  retryCount: number;
};

export type PlaybackEvent = {
  id: number;
  trackId: number;
  ts: string;
  context?: string | null;
  completionRate?: number | null;
  skipped: boolean;
};

export type RecentPlayRecord = {
  id: number;
  trackId: number;
  artist: string;
  title: string;
  ts: string;
  completionRate?: number | null;
  skipped: boolean;
};

export type TrackDetail = {
  track: TrackRecord;
  scores?: TrackScores | null;
};

export type DuplicateCluster = {
  tracks: TrackRecord[];
};

export type ProviderHealth = {
  providerKey: string;
  status: string;
  failureCount: number;
  lastFailure?: string | null;
  lastSuccess?: string | null;
  circuitOpen: boolean;
  lastCheck: string;
};

export type DiagnosticsReport = {
  status: string;
  checks: Record<string, ComponentHealth>;
  stats: SystemStats;
};

export type ComponentHealth = {
  status: string;
  message: string;
  error?: string | null;
};

export type SystemStats = {
  totalTracks: number;
  totalPlaylists: number;
  pendingAcquisitions: number;
  libraryRoots: number;
  enrichedTracks: number;
  likedTracks: number;
};

export type ProviderValidationResult = {
  providerKey: string;
  valid: boolean;
  latencyMs: number;
  error?: string | null;
  detail?: string | null;
};

export type ExplainPayload = {
  trackId: number;
  reasons: string[];
  confidence: number;
  source: string;
};

export type RecommendationResult = {
  track: TrackRecord;
  score: number;
};

