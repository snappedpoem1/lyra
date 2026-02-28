import { DIMENSIONS } from "@/types/dimensions";
import type {
  BootStatus,
  OracleRecommendation,
  PlaylistDetail,
  PlaylistSummary,
  QueueState,
  SearchResultGroup,
  TrackDossier,
  TrackListItem,
} from "@/types/domain";

function monogram(input: string): string {
  return (
    input
      .split(/\s+/)
      .map((part) => part[0]?.toUpperCase())
      .filter(Boolean)
      .slice(0, 1)
      .join("") || "L"
  );
}

export function mapTrack(row: Record<string, unknown>): TrackListItem {
  const trackId = String(row.track_id ?? row.trackId ?? crypto.randomUUID());
  const artist = String(row.artist ?? "Unknown Artist");
  const title = String(row.title ?? "Untitled");
  const scoreChips = DIMENSIONS.slice(0, 4).map((key, index) => ({
    key,
    value: typeof row[key] === "number" ? (row[key] as number) : Number((((index + trackId.length) * 0.11) % 1).toFixed(2)),
    label: key,
  }));

  return {
    trackId,
    artist,
    title,
    album: row.album ? String(row.album) : undefined,
    year: row.year ? String(row.year) : undefined,
    versionType: row.version_type ? String(row.version_type) : undefined,
    confidence: typeof row.confidence === "number" ? row.confidence : undefined,
    durationSec: typeof row.duration === "number" ? row.duration : undefined,
    artUrl: null,
    streamUrl: `/api/stream/${trackId}`,
    scoreChips,
    reason: row.reason ? String(row.reason) : `${artist} shaped for this thread.`,
    provenance: row.provenance ? String(row.provenance) : "Local library object",
  };
}

export function mapPlaylists(payload: any): PlaylistSummary[] {
  const vibes = Array.isArray(payload?.vibes) ? payload.vibes : [];
  return vibes.map((vibe: any, index: number) => ({
    id: String(vibe.name ?? `playlist-${index}`),
    kind: "vibe",
    title: String(vibe.name ?? `Playlist ${index + 1}`),
    subtitle: String(vibe.query ?? "Semantic ritual"),
    narrative: vibe.query
      ? `Built from the prompt: ${vibe.query}`
      : "A saved emotional thread from the Lyra oracle.",
    trackCount: Number(vibe.track_count ?? vibe.count ?? 0),
    freshnessLabel: "Saved vibe",
    coverMosaic: [monogram(String(vibe.name ?? "L"))],
    emotionalSignature: [
      { key: "energy", value: 0.55 },
      { key: "warmth", value: 0.62 },
      { key: "space", value: 0.67 },
      { key: "nostalgia", value: 0.58 },
    ],
    lastTouchedLabel: "Just now",
  }));
}

export function mapPlaylistDetail(summary: PlaylistSummary, payload: any, pivots: OracleRecommendation[]): PlaylistDetail {
  const tracks = Array.isArray(payload?.tracks)
    ? payload.tracks.map((row: any) => mapTrack(row))
    : [];

  const arc = tracks.slice(0, 6).map((track: TrackListItem, index: number) => ({
    step: index + 1,
    energy: track.scoreChips.find((chip: TrackListItem["scoreChips"][number]) => chip.key === "energy")?.value ?? 0.5,
    valence: track.scoreChips.find((chip: TrackListItem["scoreChips"][number]) => chip.key === "valence")?.value ?? 0.5,
    tension: track.scoreChips.find((chip: TrackListItem["scoreChips"][number]) => chip.key === "tension")?.value ?? 0.5,
  }));

  return {
    summary,
    arc,
    tracks,
    storyBeats: [
      "Open the room with distance and invitation.",
      "Increase pressure without breaking the spell.",
      "Leave residue, not closure.",
    ],
    oraclePivots: pivots,
    relatedPlaylists: [],
  };
}

export function mapSearch(payload: any, playlists: PlaylistSummary[], pivots: OracleRecommendation[]): SearchResultGroup {
  const tracks = Array.isArray(payload?.results) ? payload.results.map((row: any) => mapTrack(row)) : [];
  return {
    query: String(payload?.original_query ?? payload?.query ?? ""),
    rewrittenQuery: payload?.rewrite?.query ? String(payload.rewrite.query) : undefined,
    tracks,
    playlists,
    versions: [],
    oraclePivots: pivots,
  };
}

export function mapRadioQueue(payload: any): QueueState {
  const items = Array.isArray(payload?.queue) ? payload.queue.map((row: any) => mapTrack(row)) : [];
  return {
    queueId: crypto.randomUUID(),
    origin: String(payload?.mode ?? "oracle"),
    algorithm: String(payload?.mode ?? "oracle"),
    generatedAt: new Date().toISOString(),
    reorderable: true,
    currentIndex: 0,
    items,
  };
}

export function mapBootStatus(payload: any): BootStatus {
  return {
    ready: true,
    service: String(payload?.service ?? "lyra-oracle"),
    version: String(payload?.version ?? "1.0"),
    message: String(payload?.message ?? payload?.status ?? "Wake state aligned."),
  };
}

export function mapDossier(track: TrackListItem, structurePayload: any, lorePayload: any, dnaPayload: any): TrackDossier {
  const scores = Object.fromEntries(
    DIMENSIONS.map((key) => [key, track.scoreChips.find((chip) => chip.key === key)?.value ?? null]),
  ) as TrackDossier["scores"];

  const structure = structurePayload?.structure
    ? {
        bpm: structurePayload.structure.bpm,
        key: structurePayload.structure.key_signature,
        hasDrop: Boolean(structurePayload.structure.has_drop),
        dropTimestamp: structurePayload.structure.drop_timestamp,
        energyProfile: Array.isArray(structurePayload.structure.energy_profile)
          ? structurePayload.structure.energy_profile
          : [],
      }
    : undefined;

  const lineage = Array.isArray(lorePayload?.connections)
    ? lorePayload.connections.map((item: any) => ({
        source: String(item.source ?? track.artist),
        target: String(item.target ?? "Unknown"),
        type: String(item.type ?? "lineage"),
        weight: typeof item.weight === "number" ? item.weight : 0.5,
      }))
    : [];

  const samples = Array.isArray(dnaPayload?.samples)
    ? dnaPayload.samples.map((item: any) => ({
        artist: String(item.original_artist ?? item.artist ?? "Unknown"),
        title: String(item.original_title ?? item.title ?? "Unknown"),
        year: typeof item.original_year === "number" ? item.original_year : undefined,
        confidence: typeof item.confidence === "number" ? item.confidence : undefined,
      }))
    : [];

  return {
    track,
    filepath: String(track.provenance ?? "Local library object"),
    fileType: track.streamUrl.endsWith(".flac") ? "FLAC" : "Library Stream",
    scores,
    structure,
    lineage,
    samples,
    remixes: null,
    provenanceNotes: [track.provenance ?? "Local file held in the altar.", "Metadata reconciled for listening-first inspection."],
    acquisitionNotes: ["Guarded import path assumed.", "Full acquisition thread not yet surfaced in UI."],
  };
}
