import type { DimensionKey } from "@/types/dimensions";

export type PlaylistKind = "vibe" | "oracle_queue" | "ritual" | "manual";
export type PlaybackStatus = "idle" | "loading" | "playing" | "paused" | "ended" | "error";
export type RightRailTab = "now-playing" | "queue" | "details";
export type OracleMode = "flow" | "chaos" | "discovery" | "constellation";
export type ConnectionState = "LIVE" | "DEGRADED" | "FIXTURE";

export interface ScoreChip {
  key: DimensionKey;
  value: number | null;
  label: string;
}

export interface TrackListItem {
  trackId: string;
  artist: string;
  title: string;
  album?: string;
  year?: string;
  durationSec?: number;
  versionType?: string;
  confidence?: number;
  artUrl?: string | null;
  streamUrl: string;
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

export interface ConstellationNode {
  id: string;
  label: string;
  kind: "track" | "playlist" | "artist" | "mood" | "pivot";
  weight: number;
  x?: number;
  y?: number;
  accent?: string;
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
