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
  composerProviderPreference: string;
  composerDefaultTrackCount: number;
  composerExplanationDepth: string;
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
  queuePosition: number;
  priorityScore: number;
  source?: string | null;
  addedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  failedAt?: string | null;
  cancelledAt?: string | null;
  error?: string | null;
  statusMessage?: string | null;
  failureStage?: string | null;
  failureReason?: string | null;
  failureDetail?: string | null;
  retryCount: number;
  selectedProvider?: string | null;
  selectedTier?: string | null;
  workerLabel?: string | null;
  validationConfidence?: number | null;
  validationSummary?: string | null;
  targetRootId?: number | null;
  targetRootPath?: string | null;
  outputPath?: string | null;
  downstreamTrackId?: number | null;
  scanCompleted: boolean;
  organizeCompleted: boolean;
  indexCompleted: boolean;
  cancelRequested: boolean;
  lifecycleStage?: string | null;
  lifecycleProgress?: number | null;
  lifecycleNote?: string | null;
  updatedAt?: string | null;
};

export type AcquisitionPreflightCheck = {
  key: string;
  label: string;
  status: string;
  detail: string;
};

export type AcquisitionPreflight = {
  ready: boolean;
  pythonAvailable: boolean;
  downloaderAvailable: boolean;
  diskOk: boolean;
  libraryRootOk: boolean;
  outputPathOk: boolean;
  freeBytes: number;
  requiredBytes: number;
  checks: AcquisitionPreflightCheck[];
  notes: string[];
};

export type AcquisitionEventPayload = {
  queue: AcquisitionQueueItem[];
  workerRunning: boolean;
  latestItemId?: number | null;
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

export type ArtistConnection = {
  artist: string;
  score: number;
};

export type ArtistProfile = {
  artist: string;
  trackCount: number;
  albumCount: number;
  albums: string[];
  genres: string[];
  bio?: string | null;
  imageUrl?: string | null;
  lastfmUrl?: string | null;
  primaryMbid?: string | null;
  identityConfidence: number;
  provenance: EnrichmentEntry[];
  topTracks: TrackRecord[];
  connections: ArtistConnection[];
};

// G-061: Enrichment Provenance
export type EnrichmentEntry = {
  provider: string;
  status: string;
  confidence: number;
  note?: string | null;
  mbid?: string | null;
  releaseMbid?: string | null;
  releaseTitle?: string | null;
  releaseDate?: string | null;
  matchScore?: number | null;
  listeners?: number | null;
  playCount?: number | null;
  tags: string[];
  wikiSummary?: string | null;
  year?: number | null;
  genres: string[];
  label?: string | null;
  lyricsUrl?: string | null;
  hasLrc?: boolean | null;
};

export type TrackEnrichmentResult = {
  trackId: number;
  enrichmentState: string;
  entries: EnrichmentEntry[];
  primaryMbid?: string | null;
  identityConfidence: number;
  degradedProviders: string[];
};

// G-062: Curation Workflows
export type CurationLogEntry = {
  logId: number;
  action: string;
  trackIds: number[];
  detail: string;
  createdAt: string;
  undone: boolean;
};

export type CleanupIssue = {
  issueType: string;
  trackId: number;
  currentValue: string;
  suggestedValue: string;
  severity: string;
};

export type LibraryCleanupPreview = {
  issues: CleanupIssue[];
};

// G-063: Playlist Intelligence
export type PlaylistTrackWithReason = {
  track: TrackRecord;
  reason: string;
  position: number;
};

export type PlaylistIntentState = {
  energy: string;
  descriptors: string[];
};

export type PlaylistIntent = {
  prompt: string;
  promptRole: string;
  sourceEnergy: string;
  destinationEnergy: string;
  openingState: PlaylistIntentState;
  landingState: PlaylistIntentState;
  transitionStyle: string;
  emotionalArc: string[];
  textureDescriptors: string[];
  explicitEntities: string[];
  familiarityVsNovelty: string;
  discoveryAggressiveness: string;
  userSteer: string[];
  exclusions: string[];
  explanationDepth: string;
  sequencingNotes: string[];
  confidenceNotes: string[];
  confidence: number;
};

export type ComposerProviderStatus = {
  requestedProvider: string;
  selectedProvider: string;
  providerKind: string;
  mode: string;
  fallbackReason?: string | null;
};

export type PlaylistPhase = {
  key: string;
  label: string;
  summary: string;
  targetEnergy: number;
  targetValence: number;
  targetTension: number;
  targetWarmth: number;
  targetSpace: number;
  noveltyBias: number;
};

export type TrackReasonPayload = {
  summary: string;
  phase: string;
  whyThisTrack: string;
  transitionNote: string;
  evidence: string[];
  explicitFromPrompt: string[];
  inferredByLyra: string[];
  confidence: number;
};

export type ComposedPlaylistTrack = {
  track: TrackRecord;
  phaseKey: string;
  phaseLabel: string;
  fitScore: number;
  reason: TrackReasonPayload;
  position: number;
};

export type ComposedPlaylistDraft = {
  name: string;
  prompt: string;
  intent: PlaylistIntent;
  providerStatus: ComposerProviderStatus;
  phases: PlaylistPhase[];
  narrative?: string | null;
  tracks: ComposedPlaylistTrack[];
};

export type ComposerAction = "playlist" | "bridge" | "discovery" | "explain" | "steer";

export type BridgeStep = {
  track: TrackRecord;
  fitScore: number;
  role: string;
  why: string;
  distanceFromSource: number;
  distanceFromDestination: number;
};

export type BridgePath = {
  sourceLabel: string;
  destinationLabel: string;
  steps: BridgeStep[];
  narrative?: string | null;
  confidence: number;
  alternateDirections: string[];
};

export type DiscoveryDirection = {
  label: string;
  description: string;
  tracks: ComposedPlaylistTrack[];
  why: string;
};

export type DiscoveryRoute = {
  seedLabel: string;
  directions: DiscoveryDirection[];
  narrative?: string | null;
  confidence: number;
};

export type SteerPayload = {
  noveltyBias?: number | null;
  energyBias?: number | null;
  warmthBias?: number | null;
  adventurousness?: number | null;
  contrastSharpness?: number | null;
  explanationDepth?: string | null;
};

export type ComposerResponse = {
  action: ComposerAction;
  prompt: string;
  intent: PlaylistIntent;
  providerStatus: ComposerProviderStatus;
  draft?: ComposedPlaylistDraft | null;
  bridge?: BridgePath | null;
  discovery?: DiscoveryRoute | null;
  explanation?: string | null;
  activeRole: string;
  uncertainty: string[];
  alternativesConsidered: string[];
};

export type GeneratedPlaylist = {
  name: string;
  intent: string;
  narrative?: string;
  tracks: PlaylistTrackWithReason[];
};

// G-064: Discovery Graph Depth
export type RelatedArtist = {
  name: string;
  connectionStrength: number;
  connectionType: string;
  localTrackCount: number;
};

export type DiscoveryInteraction = {
  artistName: string;
  action: string;
  createdAt: string;
};

export type DiscoverySession = {
  recent: DiscoveryInteraction[];
};

export type GraphNode = {
  artist: string;
  degree: number;
};

export type GraphStats = {
  totalArtists: number;
  totalConnections: number;
  topConnected: GraphNode[];
};
