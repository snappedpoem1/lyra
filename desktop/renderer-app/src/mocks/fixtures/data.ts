import { DIMENSIONS } from "@/types/dimensions";
import type {
  BootStatus,
  ConstellationEdge,
  ConstellationNode,
  DoctorCheck,
  OracleRecommendation,
  PlaylistDetail,
  PlaylistSummary,
  SearchResultGroup,
  TrackDossier,
  TrackListItem,
  VersionCluster,
} from "@/types/domain";

const buildChips = (seed = 0): TrackListItem["scoreChips"] =>
  DIMENSIONS.map((key, index) => {
    const raw = ((seed * 17 + index * 9) % 100) / 100;
    return {
      key,
      value: Number(raw.toFixed(2)),
      label: raw > 0.7 ? `high ${key}` : raw < 0.33 ? `low ${key}` : key,
    };
  });

export const tracks: TrackListItem[] = [
  {
    trackId: "lyra-001",
    artist: "Burial",
    title: "Untrue (Oracle Cut)",
    path: "/fixtures/Burial/Untrue (Oracle Cut).flac",
    album: "Night Transit",
    year: "2026",
    durationSec: 289,
    versionType: "alt mix",
    confidence: 0.92,
    streamUrl: "/api/stream/lyra-001",
    reasons: [{ type: "semantic", text: "High warmth and space scores match your current listening profile.", score: 0.92 }],
    scoreChips: buildChips(1),
    reason: "High warmth and space scores match your current listening profile.",
    provenance: "Local FLAC, verified",
    structureHint: { bpm: 134, hasDrop: false },
  },
  {
    trackId: "lyra-002",
    artist: "Massive Attack",
    title: "Angel in Static",
    path: "/fixtures/Massive Attack/Angel in Static.flac",
    album: "Midnight Signals",
    year: "2024",
    durationSec: 372,
    confidence: 0.88,
    streamUrl: "/api/stream/lyra-002",
    reasons: [{ type: "semantic", text: "Strong tension and density scores. Similar to recently played tracks.", score: 0.88 }],
    scoreChips: buildChips(2),
    reason: "Strong tension and density scores. Similar to recently played tracks.",
    provenance: "Local ALAC, curated",
    structureHint: { bpm: 98, hasDrop: true },
  },
  {
    trackId: "lyra-003",
    artist: "Portishead",
    title: "Cathedral Dust",
    path: "/fixtures/Portishead/Cathedral Dust.flac",
    album: "Dummy Echoes",
    year: "2025",
    durationSec: 241,
    streamUrl: "/api/stream/lyra-003",
    reasons: [{ type: "semantic", text: "High rawness and nostalgia. Bridges trip-hop and ambient.", score: 0.84 }],
    scoreChips: buildChips(3),
    reason: "High rawness and nostalgia. Bridges trip-hop and ambient.",
    provenance: "Local FLAC",
    structureHint: { bpm: 84, hasDrop: false },
  },
  {
    trackId: "lyra-004",
    artist: "Nils Frahm",
    title: "Ash Bloom",
    path: "/fixtures/Nils Frahm/Ash Bloom.wav",
    album: "Rooms for Ghost Light",
    year: "2026",
    durationSec: 423,
    streamUrl: "/api/stream/lyra-004",
    reasons: [{ type: "semantic", text: "Peak space and complexity scores. Low play count despite high match.", score: 0.9 }],
    scoreChips: buildChips(4),
    reason: "Peak space and complexity scores. Low play count despite high match.",
    provenance: "Local WAV, hand-tagged",
    structureHint: { bpm: 72, hasDrop: false },
  },
];

export const bootStatus: BootStatus = {
  ready: true,
  service: "lyra-oracle",
  version: "1.0",
  message: "Connected",
};

export const doctorChecks: DoctorCheck[] = [
  { name: "Python", status: "PASS", details: "3.12.2" },
  { name: "Database", status: "PASS", details: "Writable: lyra_registry.db" },
  { name: "ChromaDB (local)", status: "WARNING", details: "Fixture mode using sample diagnostics" },
  { name: "LLM (fixture)", status: "FAIL", details: "Backend offline in fixture mode" },
];

export const playlistSummaries: PlaylistSummary[] = [
  {
    id: "after-midnight-ritual",
    kind: "vibe",
    title: "After Midnight",
    subtitle: "Low energy, high warmth, spacious",
    narrative: "Late-night listening with warm analog textures and deep sub-bass.",
    trackCount: 24,
    freshnessLabel: "Updated today",
    coverMosaic: ["B", "M", "P", "N"],
    emotionalSignature: [
      { key: "energy", value: 0.54 },
      { key: "warmth", value: 0.8 },
      { key: "space", value: 0.72 },
      { key: "nostalgia", value: 0.68 },
    ],
    lastTouchedLabel: "13 minutes ago",
  },
  {
    id: "cathedral-bass-memory",
    kind: "vibe",
    title: "Cathedral Bass",
    subtitle: "Vast, heavy, textured",
    narrative: "Deep bass with reverb-heavy atmospherics and slow builds.",
    trackCount: 17,
    freshnessLabel: "Recent",
    coverMosaic: ["C", "B", "M", "R"],
    emotionalSignature: [
      { key: "energy", value: 0.44 },
      { key: "space", value: 0.9 },
      { key: "tension", value: 0.66 },
      { key: "nostalgia", value: 0.74 },
    ],
    lastTouchedLabel: "Yesterday",
  },
];

export const oracleRecommendations: OracleRecommendation[] = [
  {
    id: "oracle-flow-1",
    mode: "flow",
    title: "Continue current mood",
    rationale: "Matched on warmth, space, and moderate tension from your recent plays.",
    confidenceLabel: "92% match",
    seedLabel: "After Midnight",
    previewTracks: [tracks[1], tracks[2], tracks[3]],
    actions: ["play-now", "replace-queue", "append-queue", "open-constellation"],
  },
  {
    id: "oracle-discovery-1",
    mode: "discovery",
    title: "Underplayed gems in your library",
    rationale: "High-scoring tracks you haven't listened to recently.",
    confidenceLabel: "86% match",
    seedLabel: "Taste profile",
    previewTracks: [tracks[3], tracks[0]],
    actions: ["play-now", "append-queue", "save-playlist", "open-constellation"],
  },
];

export const playlistDetails: Record<string, PlaylistDetail> = {
  "after-midnight-ritual": {
    summary: playlistSummaries[0],
    arc: [
      { step: 1, energy: 0.18, valence: 0.33, tension: 0.52 },
      { step: 2, energy: 0.36, valence: 0.41, tension: 0.57 },
      { step: 3, energy: 0.58, valence: 0.48, tension: 0.69 },
      { step: 4, energy: 0.71, valence: 0.45, tension: 0.74 },
      { step: 5, energy: 0.44, valence: 0.37, tension: 0.61 },
    ],
    tracks,
    storyBeats: [
      "Open with ambient textures, low energy.",
      "Gradually introduce rhythm and build tension.",
      "Peak energy mid-playlist, then ease down.",
      "Close with warmth and resolution.",
    ],
    oraclePivots: oracleRecommendations,
    relatedPlaylists: [playlistSummaries[1]],
  },
  "cathedral-bass-memory": {
    summary: playlistSummaries[1],
    arc: [
      { step: 1, energy: 0.28, valence: 0.39, tension: 0.36 },
      { step: 2, energy: 0.48, valence: 0.42, tension: 0.44 },
      { step: 3, energy: 0.64, valence: 0.46, tension: 0.54 },
      { step: 4, energy: 0.31, valence: 0.35, tension: 0.33 },
    ],
    tracks: [...tracks].reverse(),
    storyBeats: [
      "Start spacious and open.",
      "Build low-end presence gradually.",
      "Resolve with sustained warmth.",
    ],
    oraclePivots: [oracleRecommendations[1]],
    relatedPlaylists: [playlistSummaries[0]],
  },
};

export const versionCluster: VersionCluster = {
  canonicalLabel: "Untrue / variants",
  primary: tracks[0],
  alternates: [tracks[2]],
  remixes: [tracks[1]],
  liveCuts: [tracks[3]],
  confidence: 0.77,
};

export const searchResults: SearchResultGroup = {
  query: "deep bass with warm analog texture",
  rewrittenQuery: "bass-heavy nocturnal trip-hop with warm analog texture and spatial atmospherics",
  tracks,
  playlists: playlistSummaries,
  versions: [versionCluster],
  oraclePivots: oracleRecommendations,
};

export const dossier: TrackDossier = {
  track: tracks[0],
  filepath: "/library/Burial/Untrue (Oracle Cut).flac",
  fileType: "FLAC",
  scores: Object.fromEntries(DIMENSIONS.map((key, index) => [key, ((index + 2) * 0.08) % 1])) as TrackDossier["scores"],
  structure: {
    bpm: 134,
    key: "F#m",
    hasDrop: false,
    energyProfile: [0.12, 0.18, 0.26, 0.38, 0.51, 0.57, 0.49, 0.35],
  },
  lineage: [
    { source: "Burial", target: "Massive Attack", type: "lineage", weight: 0.66 },
    { source: "Untrue (Oracle Cut)", target: "After Midnight", type: "playlist", weight: 0.84 },
  ],
  samples: [{ artist: "Unknown Choir", title: "Cathedral Fragment", year: 1997, confidence: 0.51 }],
  remixes: versionCluster,
  provenanceNotes: [
    "Local FLAC file in active library.",
    "Scores: high warmth (0.80), high nostalgia (0.68).",
  ],
  acquisitionNotes: [
    "Passed guard validation.",
    "Metadata reconciled via MusicBrainz.",
  ],
};

export const constellationNodes: ConstellationNode[] = [
  { id: "playlist-1", label: "After Midnight", kind: "playlist", weight: 1, accent: "#f0a44b", playlistId: "after-midnight-ritual" },
  { id: "track-1", label: tracks[0].title, kind: "track", weight: 0.82, accent: "#ffd38a", trackId: tracks[0].trackId },
  { id: "track-2", label: tracks[1].title, kind: "track", weight: 0.78, accent: "#d78e4d", trackId: tracks[1].trackId },
  { id: "mood-1", label: "Warm + Spacious", kind: "mood", weight: 0.62, accent: "#f3c68b" },
  { id: "pivot-1", label: "Discovery", kind: "pivot", weight: 0.7, accent: "#f5b05f" },
];

export const constellationEdges: ConstellationEdge[] = [
  { id: "e1", source: "playlist-1", target: "track-1", relationship: "oracle", strength: 0.92, reason: "Core track in this playlist" },
  { id: "e2", source: "track-1", target: "track-2", relationship: "similarity", strength: 0.64, reason: "Similar bass weight and space scores" },
  { id: "e3", source: "track-1", target: "mood-1", relationship: "mood", strength: 0.74, reason: "High warmth, tension, and nostalgia" },
  { id: "e4", source: "mood-1", target: "pivot-1", relationship: "oracle", strength: 0.59, reason: "Underplayed tracks matching this profile" },
];
