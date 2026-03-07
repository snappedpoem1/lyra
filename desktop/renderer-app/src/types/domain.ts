import type { DimensionKey } from "@/types/dimensions";

export type PlaylistKind = "vibe" | "oracle_queue" | "ritual" | "manual" | "saved";
export type PlaybackStatus = "idle" | "loading" | "playing" | "paused" | "ended" | "error";
export type RightRailTab = "now-playing" | "queue" | "details";
export type OracleMode = "flow" | "chaos" | "discovery" | "constellation";
export type ConnectionState = "LIVE" | "DEGRADED" | "FIXTURE";
export type RecommendationNoveltyBand = "safe" | "stretch" | "chaos";
export type RecommendationProvider = "local" | "lastfm" | "listenbrainz";

export interface ScoreChip {
  key: DimensionKey;
  value: number | null;
  label: string;
}

export interface TrackReason {
  type: string;
  text: string;
  score: number;
}

export interface TrackListItem {
  trackId: string;
  artist: string;
  title: string;
  path: string;
  album?: string;
  year?: string;
  durationSec?: number;
  versionType?: string;
  confidence?: number;
  artUrl?: string | null;
  streamUrl?: string;
  reasons: TrackReason[];
  scoreChips: ScoreChip[];
  reason?: string;
  provenance?: string;
  structureHint?: { bpm?: number; hasDrop?: boolean };
}

export interface PlaylistSummary {
  id: string;
  kind: PlaylistKind;
  title: string;
  subtitle: string;
  narrative: string;
  trackCount: number;
  freshnessLabel: string;
  coverMosaic: string[];
  emotionalSignature: Array<{ key: DimensionKey; value: number }>;
  lastTouchedLabel?: string;
}

export interface OracleRecommendation {
  id: string;
  mode: OracleMode;
  title: string;
  rationale: string;
  confidenceLabel: string;
  seedLabel?: string;
  previewTracks: TrackListItem[];
  actions: Array<"play-now" | "replace-queue" | "append-queue" | "save-playlist" | "open-constellation">;
}

export type RecommendationAvailability = "local" | "acquisition-lead" | "unresolved";

export interface EvidenceItem {
  type: string;
  source: string;
  weight: number;
  text: string;
  rawValue?: unknown;
}

export interface RecommendationProviderSignal {
  provider: RecommendationProvider | string;
  label: string;
  score: number;
  rawScore: number;
  reason: string;
}

export interface ProviderError {
  code: string;
  message: string;
  detail?: string;
}

export interface ProviderReport {
  provider: string;
  status: "ok" | "empty" | "degraded" | "failed";
  message: string;
  seedContext: string;
  candidates: Array<Record<string, unknown>>;
  errors: ProviderError[];
  timingMs: number;
}

export interface RecommendationProviderStatus {
  available: boolean;
  used: boolean;
  weight: number;
  message: string;
  matchedLocalTracks: number;
  acquisitionCandidates: number;
}

export interface AcquisitionLead {
  artist: string;
  title: string;
  provider: RecommendationProvider | string;
  reason: string;
  score: number;
  evidence: EvidenceItem[];
}

export interface BrokeredRecommendation {
  track: TrackListItem;
  brokerScore: number;
  primaryReason: string;
  providerSignals: RecommendationProviderSignal[];
  evidence: EvidenceItem[];
  confidence: number;
  noveltyBandFit: string;
  availability: RecommendationAvailability;
  explanation: string;
}

export interface RecommendationBrokerResponse {
  schemaVersion: string;
  mode: string;
  noveltyBand: RecommendationNoveltyBand;
  seedTrackId?: string;
  seedTrack?: TrackListItem | null;
  providerWeights: Record<string, number>;
  providerStatus: Record<string, RecommendationProviderStatus>;
  providerReports: ProviderReport[];
  recommendations: BrokeredRecommendation[];
  acquisitionLeads: AcquisitionLead[];
  degraded: boolean;
  degradationSummary: string;
}

export interface PlaylistDetail {
  summary: PlaylistSummary;
  arc: Array<{ step: number; energy: number; valence: number; tension: number }>;
  tracks: TrackListItem[];
  storyBeats: string[];
  oraclePivots: OracleRecommendation[];
  relatedPlaylists: PlaylistSummary[];
}

export interface NowPlayingState {
  track: TrackListItem | null;
  status: PlaybackStatus;
  currentTimeSec: number;
  durationSec: number;
  progress: number;
  volume: number;
  muted: boolean;
  repeatMode: "off" | "one" | "all";
  shuffle: boolean;
  sourceLabel?: string;
  explanation?: string;
  visualizerMode: "waveform" | "spectrum" | "bloom";
}

export interface QueueState {
  queueId: string;
  origin: string;
  algorithm?: string;
  generatedAt?: string;
  reorderable: boolean;
  currentIndex: number;
  items: TrackListItem[];
}

export interface LibraryArtistDetail {
  artist: string;
  trackCount: number;
  albumCount: number;
  years: string[];
  albums: Array<{ name: string; count: number }>;
  tracks: TrackListItem[];
}

export interface LibraryAlbumDetail {
  artist: string;
  album: string;
  trackCount: number;
  years: string[];
  tracks: TrackListItem[];
}

export interface VersionCluster {
  canonicalLabel: string;
  primary?: TrackListItem;
  alternates: TrackListItem[];
  remixes: TrackListItem[];
  liveCuts: TrackListItem[];
  confidence?: number;
}

export interface TrackDossier {
  track: TrackListItem;
  filepath?: string;
  fileType?: string;
  scores: Record<DimensionKey, number | null>;
  lyrics?: {
    provider?: string;
    state?: string;
    excerpt?: string;
    releaseDate?: string;
    annotationCount?: number;
    pageviews?: number;
    url?: string;
    artUrl?: string;
  };
  structure?: { bpm?: number; key?: string; hasDrop?: boolean; dropTimestamp?: number; energyProfile?: number[] };
  lineage?: Array<{ source: string; target: string; type: string; weight?: number }>;
  samples?: Array<{ artist: string; title: string; year?: number; confidence?: number }>;
  remixes?: VersionCluster | null;
  provenanceNotes: string[];
  acquisitionNotes: string[];
  fact?: string;
}

export interface SearchResultGroup {
  query: string;
  rewrittenQuery?: string;
  tracks: TrackListItem[];
  playlists: PlaylistSummary[];
  versions: VersionCluster[];
  oraclePivots: OracleRecommendation[];
}

export interface PlaylistRunSummary {
  uuid: string;
  prompt?: string;
  createdAt?: string;
  tracks: TrackListItem[];
}

export interface VibeGenerateMeta {
  prompt: string;
  generated?: {
    query?: string;
    name?: string;
    n?: number;
    [key: string]: unknown;
  };
  savedAs?: string | null;
}

export interface VibeGenerateResult {
  meta: VibeGenerateMeta;
  run: PlaylistRunSummary;
}

export interface VibeCreateResult {
  prompt: string;
  name: string;
  generated?: {
    query?: string;
    name?: string;
    n?: number;
    [key: string]: unknown;
  };
  save: {
    status?: string;
    name?: string;
    query?: string;
    track_count?: number;
    [key: string]: unknown;
  };
}

export interface ConstellationNode {
  id: string;
  label: string;
  kind: "track" | "playlist" | "artist" | "mood" | "pivot";
  weight: number;
  x?: number;
  y?: number;
  accent?: string;
  inLibrary?: boolean;
  trackId?: string;
  playlistId?: string;
}

export interface ConstellationEdge {
  id: string;
  source: string;
  target: string;
  relationship: "similarity" | "lineage" | "version" | "mood" | "oracle";
  strength: number;
  reason?: string;
}

export interface VisualizerFrame {
  waveform: number[];
  spectrum: number[];
  energy: number;
  tension: number;
  movement: number;
  isPlaying: boolean;
}

export interface BootStatus {
  ready: boolean;
  service: string;
  version: string;
  message: string;
  phase?: string;
  state?: ConnectionState;
  diagnostics?: Record<string, unknown>;
}

export interface DoctorCheck {
  name: string;
  status: "PASS" | "WARNING" | "FAIL";
  details: string;
}

export interface DoctorReport {
  status: string;
  overall: "PASS" | "WARNING" | "FAIL";
  count: number;
  summary: Record<string, number>;
  checks: DoctorCheck[];
}

export interface AgentResponse {
  action: string;
  thought: string;
  intent: Record<string, unknown>;
  next: Record<string, unknown> | string;
  response?: string;
  observation?: unknown;
  llm?: { ok: boolean; model?: string; error?: string };
}

export interface AgentFactDrop {
  track_id: string;
  fact: string | null;
}

export interface AgentSuggestion {
  suggestion: string;
  action: string;
}
