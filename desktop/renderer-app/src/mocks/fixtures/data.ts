import { DIMENSIONS } from "@/types/dimensions";
import type {
  BootStatus,
  ConstellationEdge,
  ConstellationNode,
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
    album: "Night Transit",
    year: "2026",
    durationSec: 289,
    versionType: "alt mix",
    confidence: 0.92,
    streamUrl: "/api/stream/lyra-001",
    scoreChips: buildChips(1),
    reason: "Foggy percussion and warm ache hold the room without collapsing it.",
    provenance: "Local FLAC, verified",
    structureHint: { bpm: 134, hasDrop: false },
  },
  {
    trackId: "lyra-002",
    artist: "Massive Attack",
    title: "Angel in Static",
    album: "Midnight Signals",
    year: "2024",
    durationSec: 372,
    confidence: 0.88,
    streamUrl: "/api/stream/lyra-002",
    scoreChips: buildChips(2),
    reason: "Low-end pressure with enough negative space to feel dangerous.",
    provenance: "Local ALAC, curated",
    structureHint: { bpm: 98, hasDrop: true },
  },
  {
    trackId: "lyra-003",
    artist: "Portishead",
    title: "Cathedral Dust",
    album: "Dummy Echoes",
    year: "2025",
    durationSec: 241,
    streamUrl: "/api/stream/lyra-003",
    scoreChips: buildChips(3),
    reason: "Cracked intimacy and smoked-out warmth keep the ritual human.",
    provenance: "Local FLAC, library altar",
    structureHint: { bpm: 84, hasDrop: false },
  },
  {
    trackId: "lyra-004",
    artist: "Nils Frahm",
    title: "Ash Bloom",
    album: "Rooms for Ghost Light",
    year: "2026",
    durationSec: 423,
    streamUrl: "/api/stream/lyra-004",
    scoreChips: buildChips(4),
    reason: "Expansive space and memory-loaded overtones make this a bridge track.",
    provenance: "Local WAV, hand-tagged",
    structureHint: { bpm: 72, hasDrop: false },
  },
];

export const bootStatus: BootStatus = {
  ready: true,
  service: "lyra-oracle",
  version: "1.0",
  message: "Wake state aligned. Library altar responding.",
};

export const playlistSummaries: PlaylistSummary[] = [
  {
    id: "after-midnight-ritual",
    kind: "vibe",
    title: "After Midnight Ritual",
    subtitle: "Low light, nerve glow, sacred bass weight",
    narrative: "A slow-burn arc for when the room is dark enough to hear your taste thinking.",
    trackCount: 24,
    freshnessLabel: "Refreshed tonight",
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
    title: "Cathedral Bass Memory",
    subtitle: "Vast rooms, remembered pressure, elegant ruin",
    narrative: "Tracks that bloom like old neon through rain and sub-bass.",
    trackCount: 17,
    freshnessLabel: "Still glowing",
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
    title: "Hold the room, then bruise it",
    rationale: "Lyra traced warmth, space, and moderate tension to extend the ritual without flattening it.",
    confidenceLabel: "High confidence",
    seedLabel: "After Midnight Ritual",
    previewTracks: [tracks[1], tracks[2], tracks[3]],
    actions: ["play-now", "replace-queue", "append-queue", "open-constellation"],
  },
  {
    id: "oracle-discovery-1",
    mode: "discovery",
    title: "Ghost pressure from the edge of your taste map",
    rationale: "Underplayed library cuts align with your late-night bias for low-light bass and analog ache.",
    confidenceLabel: "Knife-edge match",
    seedLabel: "Recent listening memory",
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
      "Open with distance and static, not impact.",
      "Let percussion arrive like a threat remembered late.",
      "Peak in controlled bloom, not festival release.",
      "Land on warmth, not resolution.",
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
      "Begin with space you can step into.",
      "Pull the low end under the listener like a floor opening.",
      "End with a holy kind of residue.",
    ],
    oraclePivots: [oracleRecommendations[1]],
    relatedPlaylists: [playlistSummaries[0]],
  },
};

export const versionCluster: VersionCluster = {
  canonicalLabel: "Untrue / shadow variants",
  primary: tracks[0],
  alternates: [tracks[2]],
  remixes: [tracks[1]],
  liveCuts: [tracks[3]],
  confidence: 0.77,
};

export const searchResults: SearchResultGroup = {
  query: "cathedral bass with analog ache and haunted warmth",
  rewrittenQuery: "moody bass-heavy nocturnal trip hop with warm analog texture vast space and haunted melancholy",
  tracks,
  playlists: playlistSummaries,
  versions: [versionCluster],
  oraclePivots: oracleRecommendations,
};

export const dossier: TrackDossier = {
  track: tracks[0],
  filepath: "A:\\music\\Active Music\\Burial\\Untrue (Oracle Cut).flac",
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
    { source: "Untrue (Oracle Cut)", target: "After Midnight Ritual", type: "oracle", weight: 0.84 },
  ],
  samples: [{ artist: "Unknown Choir", title: "Cathedral Fragment", year: 1997, confidence: 0.51 }],
  remixes: versionCluster,
  provenanceNotes: [
    "Local file, verified in active library.",
    "Emotional profile suggests high warmth and nostalgia without collapsing into sentimentality.",
  ],
  acquisitionNotes: [
    "Passed guard validation.",
    "Metadata reconciled with local library profile.",
  ],
};

export const constellationNodes: ConstellationNode[] = [
  { id: "playlist-1", label: "After Midnight Ritual", kind: "playlist", weight: 1, accent: "#f0a44b", playlistId: "after-midnight-ritual" },
  { id: "track-1", label: tracks[0].title, kind: "track", weight: 0.82, accent: "#ffd38a", trackId: tracks[0].trackId },
  { id: "track-2", label: tracks[1].title, kind: "track", weight: 0.78, accent: "#d78e4d", trackId: tracks[1].trackId },
  { id: "mood-1", label: "Haunted Warmth", kind: "mood", weight: 0.62, accent: "#f3c68b" },
  { id: "pivot-1", label: "Discovery Vein", kind: "pivot", weight: 0.7, accent: "#f5b05f" },
];

export const constellationEdges: ConstellationEdge[] = [
  { id: "e1", source: "playlist-1", target: "track-1", relationship: "oracle", strength: 0.92, reason: "Core anchor of the ritual arc" },
  { id: "e2", source: "track-1", target: "track-2", relationship: "similarity", strength: 0.64, reason: "Shared bass pressure and nocturnal warmth" },
  { id: "e3", source: "track-1", target: "mood-1", relationship: "mood", strength: 0.74, reason: "High warmth, tension, and nostalgia" },
  { id: "e4", source: "mood-1", target: "pivot-1", relationship: "oracle", strength: 0.59, reason: "Lyra sees an adjacent underplayed thread" },
];
