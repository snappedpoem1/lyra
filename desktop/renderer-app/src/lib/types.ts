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
  composerTasteMemory: string[];
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
  tasteMemory: TasteMemorySnapshot;
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

export type SpotifyTopArtist = {
  artist: string;
  playCount: number;
  totalMsPlayed: number;
  ownedTrackCount: number;
  missingTrackCount: number;
  lastPlayedAt?: string | null;
};

export type SpotifyMissingCandidate = {
  artist: string;
  title: string;
  album?: string | null;
  spotifyUri?: string | null;
  source: string;
  playCount: number;
  lastPlayedAt?: string | null;
  alreadyQueued: boolean;
};

export type SpotifyGapSummary = {
  available: boolean;
  dbPath?: string | null;
  sourceMode: string;
  legacyImportObserved: boolean;
  lastLegacyImportAt?: string | null;
  lastLegacyImportedHistory: number;
  lastLegacyImportedLibrary: number;
  lastLegacyImportedFeatures: number;
  historyCount: number;
  libraryCount: number;
  featuresCount: number;
  ownedOverlapCount: number;
  queuedOverlapCount: number;
  recoverableMissingCount: number;
  topArtists: SpotifyTopArtist[];
  missingCandidates: SpotifyMissingCandidate[];
  summaryLines: string[];
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

export type SearchFacetBucket = {
  value: string;
  count: number;
};

export type SearchExcavationResult = {
  query: string;
  tracks: Array<{ trackId: number; artist: string; title: string; album: string; genre: string; score: number }>;
  topArtists: SearchFacetBucket[];
  topAlbums: SearchFacetBucket[];
  routeHints: string[];
};

export type LastfmSyncResult = {
  fetched: number;
  matched: number;
  written: number;
};

export type SearchSemanticCapability = {
  providerKey: string;
  status: string;
  detail: string;
  supportsQuery: boolean;
  supportsIndexing: boolean;
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

export type ComposerDiagnosticEntry = {
  id: number;
  level: string;
  eventType: string;
  prompt: string;
  action?: string | null;
  provider: string;
  mode: string;
  message: string;
  payloadJson?: string | null;
  createdAt: string;
};

export type ComposerRunRecord = {
  id: number;
  prompt: string;
  action: string;
  activeRole: string;
  summary: string;
  provider: string;
  mode: string;
  createdAt: string;
};

export type ComposerRunDetail = {
  record: ComposerRunRecord;
  response: ComposerResponse;
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

export type EvidenceItem = {
  typeLabel: string;
  source: string;
  text: string;
  weight: number;
};

export type ExplainPayload = {
  trackId: number;
  /** Composer-grade single-sentence explanation. */
  whyThisTrack: string;
  /** Legacy flat reasons list (backward compat). */
  reasons: string[];
  /** Structured evidence items at TrackReasonPayload depth. */
  evidenceItems: EvidenceItem[];
  /** Facts from the prompt or explicit library evidence. */
  explicitFromPrompt: string[];
  /** Signals inferred by Lyra from taste/graph/scout. */
  inferredByLyra: string[];
  confidence: number;
  source: string;
};

export type RecommendationResult = {
  track: TrackRecord;
  score: number;
  /** Which broker lane produced this: "local/taste", "local/deep_cut", "scout/bridge", "graph/co_play" */
  provider: string;
  /** Single-sentence reason at composer payload depth. */
  whyThisTrack: string;
  /** Structured evidence items. */
  evidence: EvidenceItem[];
};

export type AcquisitionLead = {
  artist: string;
  title: string;
  provider: string;
  score: number;
  reason: string;
  evidence: EvidenceItem[];
};

export type RecommendationBundle = {
  recommendations: RecommendationResult[];
  acquisitionLeads: AcquisitionLead[];
};

export type AcquisitionLeadOutcome = {
  artist: string;
  title: string;
  provider: string;
  status: string;
  detail: string;
  queueItemId?: number | null;
};

export type AcquisitionLeadHandoffReport = {
  outcomes: AcquisitionLeadOutcome[];
  queuedCount: number;
  duplicateCount: number;
  errorCount: number;
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

export type PlaylistTrackReasonRecord = {
  trackId: number;
  reason: string;
  reasonPayload?: TrackReasonPayload | null;
  phaseKey?: string | null;
  phaseLabel?: string | null;
  position: number;
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
  preserves: string[];
  changes: string[];
  adjacencyType: string;
  adjacencySignals: AdjacencySignal[];
  leadsToNext: string;
};

export type BridgePath = {
  sourceLabel: string;
  destinationLabel: string;
  routeFlavor: string;
  steps: BridgeStep[];
  narrative?: string | null;
  confidence: number;
  alternateDirections: string[];
  variants: RouteVariantSummary[];
};

export type DiscoveryDirection = {
  flavor: string;
  label: string;
  description: string;
  tracks: ComposedPlaylistTrack[];
  why: string;
  preserves: string[];
  changes: string[];
  adjacencySignals: AdjacencySignal[];
  riskNote: string;
  rewardNote: string;
};

export type AdjacencySignal = {
  dimension: string;
  relation: string;
  score: number;
  note: string;
};

export type RouteVariantSummary = {
  flavor: string;
  label: string;
  logic: string;
  preserves: string[];
  changes: string[];
  riskNote: string;
  rewardNote: string;
};

export type ResponsePosture = "suggestive" | "refining" | "collaborative" | "revelatory";

export type DetailDepth = "short" | "medium" | "deep";

export type ConfidenceVoice = {
  level: string;
  phrasing: string;
  shouldOfferAlternatives: boolean;
};

export type FallbackVoice = {
  active: boolean;
  label: string;
  message: string;
};

export type RouteComparison = {
  headline: string;
  summary: string;
  variants: RouteVariantSummary[];
};

export type LyraReadSurface = {
  summary: string;
  cues: string[];
  confidenceNote: string;
};

export type LyraFraming = {
  posture: ResponsePosture;
  detailDepth: DetailDepth;
  lead: string;
  rationale: string;
  presenceNote?: string | null;
  challenge?: string | null;
  vibeGuard?: string | null;
  confidence: ConfidenceVoice;
  fallback: FallbackVoice;
  routeComparison?: RouteComparison | null;
  lyraRead: LyraReadSurface;
  sidewaysTemptations: string[];
  memoryHint?: string | null;
  nextNudges: string[];
};

export type DiscoveryRoute = {
  seedLabel: string;
  primaryFlavor: string;
  sceneExit: boolean;
  directions: DiscoveryDirection[];
  narrative?: string | null;
  confidence: number;
  variants: RouteVariantSummary[];
};

export type RememberedPreference = {
  axisKey: string;
  axisLabel: string;
  preferredPole: string;
  confidence: number;
  evidenceCount: number;
  lastSeenAt: string;
  recencyNote: string;
  confidenceNote: string;
  supportingPhrases: string[];
};

export type RouteChoicePreference = {
  routeKind: string;
  action: string;
  source: string;
  note: string;
  outcome: string;
  confidence: number;
  observedAt: string;
};

export type RouteFeedbackPayload = {
  routeKind: string;
  action: string;
  outcome: string;
  source: string;
  note?: string | null;
};

export type SessionTastePosture = {
  activeSignals: string[];
  summary: string;
  confidenceNote: string;
  updatedAt: string;
};

export type TasteMemorySnapshot = {
  sessionPosture: SessionTastePosture;
  rememberedPreferences: RememberedPreference[];
  routePreferences: RouteChoicePreference[];
  summaryLines: string[];
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
  framing: LyraFraming;
  draft?: ComposedPlaylistDraft | null;
  bridge?: BridgePath | null;
  discovery?: DiscoveryRoute | null;
  explanation?: string | null;
  activeRole: string;
  uncertainty: string[];
  alternativesConsidered: string[];
  tasteMemory: TasteMemorySnapshot;
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
  why: string;
  preserves: string[];
  changes: string[];
  riskNote: string;
};

export type DiscoveryInteraction = {
  artistName: string;
  action: string;
  createdAt: string;
};

export type DiscoverySession = {
  recent: DiscoveryInteraction[];
};

export type ScoutExitLane = {
  flavor: string; // safe | interesting | dangerous
  label: string;
  description: string;
  artists: RelatedArtist[];
};

export type ScoutExitPlan = {
  seedArtist: string;
  lanes: ScoutExitLane[];
};

// G-064: Scout / genre-hunt types
export type ScoutTarget = {
  artist: string;
  title: string;
  album: string;
  year: number | null;
  genre: string;
  path: string;
  tags: string[];
  priority: number;
};

export type BridgeArtist = {
  name: string;
  genreA: string;
  genreB: string;
  trackCount: number;
  source: string; // "local" | "discogs"
};

export type MoodSearchResult = {
  trackId: number;
  artist: string;
  title: string;
  album: string;
  genre: string;
  path: string;
  source: string;
};

export type DeepCutTrack = {
  trackId: number;
  artist: string;
  title: string;
  album: string;
  genre: string;
  path: string;
  obscurityScore: number;
  acclaimScore: number;
  popularityPercentile: number;
  localPlayCount: number;
  tasteAlignment: number;
  deepCutRank: number;
  tags: string[];
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
