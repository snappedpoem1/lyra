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
  return input.trim().charAt(0).toUpperCase() || "L";
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
    versionType: row.version_type ? String(row.version_type) : row.versionType ? String(row.versionType) : undefined,
    confidence: typeof row.confidence === "number" ? row.confidence : undefined,
    durationSec: typeof row.duration === "number" ? row.duration : typeof row.durationSec === "number" ? row.durationSec : undefined,
    artUrl: null,
    streamUrl: `/api/stream/${trackId}`,
    scoreChips,
    reason: row.reason ? String(row.reason) : row.file_exists === false ? "File is indexed but missing on disk." : `${artist} belongs in this listening thread.`,
    provenance: row.filepath ? String(row.filepath) : row.provenance ? String(row.provenance) : "Local library object",
    structureHint: {
      bpm: typeof row.bpm === "number" ? row.bpm : undefined,
      hasDrop: Boolean(row.has_drop ?? false),
    },
  };
}

export function mapPlaylists(payload: { vibes: Array<Record<string, unknown>> }): PlaylistSummary[] {
  return payload.vibes.map((vibe, index) => ({
    id: String(vibe.name ?? `playlist-${index}`),
    kind: "vibe",
    title: String(vibe.name ?? `Playlist ${index + 1}`),
    subtitle: String(vibe.query ?? "Saved listening thread"),
    narrative: vibe.query ? `Built from the prompt: ${vibe.query}` : "Saved listening thread from your library.",
    trackCount: Number(vibe.track_count ?? vibe.trackCount ?? vibe.count ?? 0),
    freshnessLabel: "Saved vibe",
    coverMosaic: [monogram(String(vibe.name ?? "L"))],
    emotionalSignature: [],
    lastTouchedLabel: vibe.created_at ? new Date(Number(vibe.created_at) * 1000).toLocaleString() : "Saved",
  }));
}

export function mapPlaylistDetail(payload: Record<string, unknown>): PlaylistDetail {
  const summary: PlaylistSummary = {
    id: String(payload.id),
    kind: "vibe",
    title: String(payload.title),
    subtitle: String(payload.subtitle ?? ""),
    narrative: String(payload.narrative ?? ""),
    trackCount: Number(payload.trackCount ?? 0),
    freshnessLabel: String(payload.freshnessLabel ?? "Saved vibe"),
    coverMosaic: Array.isArray(payload.coverMosaic) ? payload.coverMosaic.map(String) : ["L"],
    emotionalSignature: [],
    lastTouchedLabel: payload.lastTouchedLabel ? String(payload.lastTouchedLabel) : undefined,
  };

  const related = Array.isArray(payload.relatedPlaylists)
    ? payload.relatedPlaylists.map((item) => ({
        id: String(item.id ?? crypto.randomUUID()),
        kind: "vibe" as const,
        title: String(item.title ?? item.id ?? "Related"),
        subtitle: String(item.subtitle ?? ""),
        narrative: String(item.narrative ?? ""),
        trackCount: Number(item.trackCount ?? 0),
        freshnessLabel: String(item.freshnessLabel ?? "Saved vibe"),
        coverMosaic: Array.isArray(item.coverMosaic) ? item.coverMosaic.map(String) : ["L"],
        emotionalSignature: [],
        lastTouchedLabel: item.lastTouchedLabel ? String(item.lastTouchedLabel) : undefined,
      }))
    : [];

  return {
    summary,
    arc: Array.isArray(payload.arc) ? payload.arc.map((row) => ({
      step: Number(row.step ?? 0),
      energy: Number(row.energy ?? 0),
      valence: Number(row.valence ?? 0),
      tension: Number(row.tension ?? 0),
    })) : [],
    tracks: Array.isArray(payload.tracks) ? payload.tracks.map((row) => mapTrack(row)) : [],
    storyBeats: Array.isArray(payload.storyBeats) ? payload.storyBeats.map(String) : [],
    oraclePivots: [],
    relatedPlaylists: related,
  };
}

export function mapBootStatus(payload: Record<string, unknown>): BootStatus {
  return {
    ready: Boolean(payload.ok),
    service: String(payload.service ?? "lyra-oracle"),
    version: String(payload.version ?? "1.0"),
    message: String(payload.status ?? "Connected"),
    state: payload.ok ? "LIVE" : "DEGRADED",
    diagnostics: payload,
  };
}

export function mapOracleRecommendations(mode: string, payload: { results: Array<Record<string, unknown>> }): OracleRecommendation[] {
  const previewTracks = payload.results.map((row) => mapTrack(row));
  return [{
    id: `oracle-${mode}`,
    mode: mode as OracleRecommendation["mode"],
    title: `Oracle ${mode}`,
    rationale: `Live ${mode} recommendations from the Lyra backend.`,
    confidenceLabel: "Live signal",
    seedLabel: "Listening thread",
    previewTracks,
    actions: ["play-now", "replace-queue", "append-queue", "open-constellation"],
  }];
}

export function mapSearch(payload: Record<string, unknown>, playlists: PlaylistSummary[]): SearchResultGroup {
  return {
    query: String(payload.original_query ?? payload.query ?? ""),
    rewrittenQuery: payload.rewrite && typeof payload.rewrite === "object" && "query" in payload.rewrite ? String(payload.rewrite.query) : undefined,
    tracks: Array.isArray(payload.results) ? payload.results.map((row) => mapTrack(row as Record<string, unknown>)) : [],
    playlists,
    versions: [],
    oraclePivots: [],
  };
}

export function mapRadioQueue(payload: { queue: Array<Record<string, unknown>>; mode: string }): QueueState {
  return {
    queueId: crypto.randomUUID(),
    origin: payload.mode,
    algorithm: payload.mode,
    generatedAt: new Date().toISOString(),
    reorderable: true,
    currentIndex: 0,
    items: payload.queue.map((row) => mapTrack(row)),
  };
}

export function mapDossier(payload: Record<string, unknown>): TrackDossier {
  const track = mapTrack(payload.track as Record<string, unknown>);
  const structurePayload = (payload.structure ?? null) as Record<string, unknown> | null;
  const scores = Object.fromEntries(
    DIMENSIONS.map((key) => [key, track.scoreChips.find((chip) => chip.key === key)?.value ?? null]),
  ) as TrackDossier["scores"];

  return {
    track,
    filepath: track.provenance,
    fileType: track.provenance?.split(".").pop()?.toUpperCase() ?? "Library Stream",
    scores,
    structure: structurePayload ? {
      bpm: typeof structurePayload.bpm === "number" ? structurePayload.bpm : 0,
      key: String(structurePayload.key_signature ?? structurePayload.key ?? ""),
      hasDrop: Boolean(structurePayload.has_drop ?? structurePayload.hasDrop),
      dropTimestamp: typeof structurePayload.drop_timestamp === "number" ? structurePayload.drop_timestamp : undefined,
      energyProfile: Array.isArray(structurePayload.energy_profile) ? structurePayload.energy_profile.map(Number) : [],
    } : undefined,
    lineage: Array.isArray(payload.lineage) ? payload.lineage.map((row) => ({
      source: String(row.source ?? track.artist),
      target: String(row.target ?? "Unknown"),
      type: String(row.type ?? "lineage"),
      weight: typeof row.weight === "number" ? row.weight : undefined,
    })) : [],
    samples: Array.isArray(payload.samples) ? payload.samples.map((row) => ({
      artist: String(row.original_artist ?? row.artist ?? "Unknown"),
      title: String(row.original_title ?? row.title ?? "Unknown"),
      year: typeof row.original_year === "number" ? row.original_year : undefined,
      confidence: typeof row.confidence === "number" ? row.confidence : undefined,
    })) : [],
    remixes: null,
    provenanceNotes: Array.isArray(payload.provenance_notes) ? payload.provenance_notes.map(String) : [],
    acquisitionNotes: Array.isArray(payload.acquisition_notes) ? payload.acquisition_notes.map(String) : [],
    fact: payload.fact ? String(payload.fact) : undefined,
  };
}
