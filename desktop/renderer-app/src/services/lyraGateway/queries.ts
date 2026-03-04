import { constellationEdges, constellationNodes, doctorChecks, dossier, oracleRecommendations, playlistDetails, playlistSummaries, searchResults } from "@/mocks/fixtures/data";
import { fixtureModeEnabled } from "@/mocks/fixtures/mode";
import { z } from "zod";
import {
  agentSuggestionSchema,
  artistShrineSchema,
  constellationSchema,
  doctorSchema,
  dossierSchema,
  healthSchema,
  libraryAlbumDetailSchema,
  libraryAlbumsSchema,
  libraryArtistDetailSchema,
  libraryArtistsSchema,
  libraryTracksSchema,
  playlistDetailSchema,
  queueSchema,
  radioResultsSchema,
  tasteProfileSchema,
  vibeCreateSchema,
  vibeGenerateSchema,
  vibesSchema,
} from "@/config/schemas";
import type {
  AgentFactDrop,
  AgentSuggestion,
  BootStatus,
  ConstellationEdge,
  ConstellationNode,
  DoctorCheck,
  DoctorReport,
  LibraryAlbumDetail,
  LibraryArtistDetail,
  OracleMode,
  OracleRecommendation,
  PlaylistDetail,
  PlaylistSummary,
  QueueState,
  SearchResultGroup,
  TrackDossier,
  TrackListItem,
  VibeCreateResult,
  VibeGenerateResult,
} from "@/types/domain";
import { requestJson } from "./client";
import { mapBootStatus, mapDoctorReport, mapDossier, mapGeneratedVibe, mapOracleRecommendations, mapPlaylistDetail, mapPlaylists, mapRadioQueue, mapTrack } from "./mappers";
import { useConnectivityStore } from "@/stores/connectivityStore";

function useFixtureFallback<T>(error: unknown, fallback: T): T {
  const message = error instanceof Error ? error.message : "Backend unavailable";
  useConnectivityStore.getState().setFixture(message);
  return fallback;
}

export async function getBootStatus(): Promise<BootStatus> {
  try {
    return mapBootStatus(await requestJson("/api/health", healthSchema, undefined, 5000, 0));
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, { ready: false, service: "lyra-oracle", version: "fixture", message: "Fixture mode", state: "FIXTURE" });
    }
    throw error;
  }
}

export async function getDoctorReport(): Promise<DoctorReport> {
  try {
    const payload = await requestJson("/api/doctor", doctorSchema, undefined, 10000, 0);
    return mapDoctorReport(payload as DoctorCheck[]);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, mapDoctorReport(doctorChecks));
    }
    throw error;
  }
}

export async function getPlaylists(): Promise<PlaylistSummary[]> {
  try {
    const payload = await requestJson("/api/vibes", vibesSchema);
    return mapPlaylists(payload);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, playlistSummaries);
    }
    throw error;
  }
}

export async function getPlaylistDetail(id: string): Promise<PlaylistDetail> {
  try {
    const payload = await requestJson(`/api/playlists/${encodeURIComponent(id)}`, playlistDetailSchema);
    return mapPlaylistDetail(payload);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, playlistDetails[id] ?? playlistDetails["after-midnight-ritual"]);
    }
    throw error;
  }
}

export async function getSearchResults(query: string): Promise<SearchResultGroup> {
  try {
    const playlists = await getPlaylists();
    const payload = await generateVibe(query);
    return {
      query: payload.meta.prompt || query,
      rewrittenQuery: typeof payload.meta.generated?.query === "string" ? payload.meta.generated.query : undefined,
      tracks: payload.run.tracks,
      playlists,
      versions: [],
      oraclePivots: [],
    };
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, { ...searchResults, query });
    }
    throw error;
  }
}

export async function generateVibe(prompt: string, save = false): Promise<VibeGenerateResult> {
  try {
    const payload = await requestJson("/api/vibes/generate", vibeGenerateSchema, {
      method: "POST",
      body: JSON.stringify({ prompt, save, n: 20 }),
    });
    return mapGeneratedVibe(payload as Record<string, unknown>);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, {
        meta: {
          prompt,
          generated: {
            query: prompt,
            n: 20,
          },
          savedAs: save ? "Fixture Vibe" : null,
        },
        run: {
          uuid: "fixture-run",
          prompt,
          createdAt: new Date().toISOString(),
          tracks: searchResults.tracks,
        },
      });
    }
    throw error;
  }
}

export async function createVibe(prompt: string, name: string): Promise<VibeCreateResult> {
  try {
    return await requestJson("/api/vibes/create", vibeCreateSchema, {
      method: "POST",
      body: JSON.stringify({ prompt, name, n: 20 }),
    });
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, {
        prompt,
        name,
        generated: {
          query: prompt,
          name,
          n: 20,
        },
        save: {
          status: "success",
          name,
          query: prompt,
          track_count: searchResults.tracks.length,
        },
      });
    }
    throw error;
  }
}

export async function getOracleRecommendations(mode: OracleMode, seedTrackId?: string): Promise<OracleRecommendation[]> {
  try {
    if (mode === "constellation") {
      return oracleRecommendations;
    }
    if (mode === "discovery") {
      const payload = await requestJson("/api/radio/discovery?count=4", radioResultsSchema);
      return mapOracleRecommendations(mode, payload);
    }
    const payload = await requestJson(`/api/radio/${mode}`, radioResultsSchema, {
      method: "POST",
      body: JSON.stringify({ count: 4, track_id: seedTrackId, seed_track: seedTrackId }),
    });
    return mapOracleRecommendations(mode, payload);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, oracleRecommendations.filter((item) => item.mode === mode || mode === "constellation"));
    }
    throw error;
  }
}

export async function getQueue(mode: OracleMode = "flow", seedTrackId?: string): Promise<QueueState> {
  try {
    const payload = await requestJson("/api/radio/queue", queueSchema, {
      method: "POST",
      body: JSON.stringify({ mode, length: 12, seed_track: seedTrackId }),
    });
    return mapRadioQueue(payload);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, {
        queueId: "fixture-queue",
        origin: mode,
        algorithm: mode,
        generatedAt: new Date().toISOString(),
        reorderable: true,
        currentIndex: 0,
        items: oracleRecommendations[0].previewTracks,
      });
    }
    throw error;
  }
}

export async function getTrackDossier(trackId: string): Promise<TrackDossier> {
  try {
    const payload = await requestJson(`/api/tracks/${encodeURIComponent(trackId)}/dossier`, dossierSchema);
    return mapDossier(payload);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, dossier);
    }
    throw error;
  }
}

export async function getLibraryTracks(
  limit = 24,
  offset = 0,
  query = "",
  artist?: string | null,
  album?: string | null,
): Promise<{
  tracks: TrackListItem[];
  total: number;
  offset: number;
  limit: number;
  query: string;
  artist: string | null;
  album: string | null;
  artists: Array<{ name: string; count: number }>;
  albums: Array<{ name: string; count: number }>;
}> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (artist?.trim()) {
    params.set("artist", artist.trim());
  }
  if (album?.trim()) {
    params.set("album", album.trim());
  }
  const payload = await requestJson(`/api/library/tracks?${params.toString()}`, libraryTracksSchema);
  return {
    tracks: payload.tracks.map((row) => mapTrack(row)),
    total: payload.total,
    offset: payload.offset,
    limit: payload.limit,
    query: payload.query ?? "",
    artist: payload.artist ?? null,
    album: payload.album ?? null,
    artists: payload.artists ?? [],
    albums: payload.albums ?? [],
  };
}

export async function getLibraryArtists(query = "", limit = 200): Promise<Array<{ name: string; count: number }>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const payload = await requestJson(`/api/library/artists?${params.toString()}`, libraryArtistsSchema);
  return payload.artists;
}

export async function getLibraryAlbums(query = "", artist?: string | null, limit = 200): Promise<Array<{ name: string; count: number }>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (artist?.trim()) {
    params.set("artist", artist.trim());
  }
  const payload = await requestJson(`/api/library/albums?${params.toString()}`, libraryAlbumsSchema);
  return payload.albums;
}

export async function getLibraryArtistDetail(artist: string): Promise<LibraryArtistDetail> {
  const payload = await requestJson(`/api/library/artists/${encodeURIComponent(artist)}`, libraryArtistDetailSchema);
  return {
    artist: payload.artist,
    trackCount: payload.track_count,
    albumCount: payload.album_count,
    years: payload.years,
    albums: payload.albums,
    tracks: payload.tracks.map((row) => mapTrack(row)),
  };
}

/** Pull biographer enrichment for an artist (bio, genres, origin). Never throws. */
export async function getLibraryArtistBio(
  artist: string,
): Promise<{ bio?: string; genres?: string[]; origin?: string; formedYear?: string; followers?: number }> {
  try {
    const data = await requestJson(
      `/api/enrichment/biographer/${encodeURIComponent(artist)}`,
      z.record(z.any()),
      undefined,
      6000,
      0,
    );
    return {
      bio: typeof data?.bio === "string" && data.bio.trim() ? data.bio : undefined,
      genres: Array.isArray(data?.genres) ? (data.genres as string[]) : [],
      origin: typeof data?.origin === "string" ? data.origin : undefined,
      formedYear: typeof data?.formed_year === "string" ? data.formed_year : undefined,
      followers: typeof data?.spotify_followers === "number" ? data.spotify_followers : undefined,
    };
  } catch {
    return {};
  }
}

export interface ArtistShrine {
  artist: string;
  bio: string;
  bioSource: string;
  images: Record<string, string>;
  wikiThumbnail: string;
  formationYear: string | number | null;
  origin: string;
  members: string[];
  scene: string;
  genres: string[];
  era: string;
  artistMbid: string;
  lastfmListeners: number | null;
  lastfmUrl: string;
  wikiUrl: string;
  socialLinks: Record<string, string>;
  relatedArtists: Array<{ target: string; type: string; weight: number }>;
  credits: Array<{ role: string; name: string; count: number }>;
  libraryStats: {
    trackCount: number;
    albumCount: number;
    albums: Array<{ album: string | null; year: string | number | null }>;
  };
}

/** Full artist shrine — combines bio, library stats, connections, credits. */
export async function getArtistShrine(artist: string): Promise<ArtistShrine> {
  const payload = await requestJson(
    `/api/artist/shrine/${encodeURIComponent(artist)}`,
    artistShrineSchema,
    undefined,
    10000,
    0,
  );
  return {
    artist: payload.artist,
    bio: payload.bio ?? "",
    bioSource: payload.bio_source ?? "none",
    images: payload.images ?? {},
    wikiThumbnail: payload.wiki_thumbnail ?? "",
    formationYear: payload.formation_year ?? null,
    origin: payload.origin ?? "",
    members: payload.members ?? [],
    scene: payload.scene ?? "",
    genres: payload.genres ?? [],
    era: payload.era ?? "",
    artistMbid: payload.artist_mbid ?? "",
    lastfmListeners: payload.lastfm_listeners ?? null,
    lastfmUrl: payload.lastfm_url ?? "",
    wikiUrl: payload.wiki_url ?? "",
    socialLinks: payload.social_links ?? {},
    relatedArtists: payload.related_artists ?? [],
    credits: payload.credits ?? [],
    libraryStats: {
      trackCount: payload.library_stats?.track_count ?? 0,
      albumCount: payload.library_stats?.album_count ?? 0,
      albums: payload.library_stats?.albums ?? [],
    },
  };
}

export async function getLibraryAlbumDetail(album: string, artist?: string | null): Promise<LibraryAlbumDetail> {
  const params = new URLSearchParams();
  if (artist?.trim()) {
    params.set("artist", artist.trim());
  }
  const query = params.toString();
  const payload = await requestJson(
    `/api/library/albums/${encodeURIComponent(album)}${query ? `?${query}` : ""}`,
    libraryAlbumDetailSchema,
  );
  return {
    artist: payload.artist,
    album: payload.album,
    trackCount: payload.track_count,
    years: payload.years,
    tracks: payload.tracks.map((row) => mapTrack(row)),
  };
}

function _mapConstellationRelationship(
  type?: string,
): ConstellationEdge["relationship"] {
  if (!type) return "oracle";
  const t = type.toLowerCase();
  if (t.includes("member") || t.includes("lineage") || t.includes("influence")) return "lineage";
  if (t.includes("collab") || t.includes("similar") || t.includes("feature")) return "similarity";
  if (t.includes("version") || t.includes("remix") || t.includes("cover")) return "version";
  if (t.includes("mood")) return "mood";
  return "oracle";
}

export async function getConstellation(
  filters: { genre?: string; era?: string; type?: string; limit?: number } = {},
): Promise<{ nodes: ConstellationNode[]; edges: ConstellationEdge[] }> {
  try {
    const params = new URLSearchParams();
    if (filters.genre) params.set("genre", filters.genre);
    if (filters.era) params.set("era", filters.era);
    if (filters.type) params.set("type", filters.type);
    if (filters.limit) params.set("limit", String(filters.limit));
    const qs = params.toString();
    const payload = await requestJson(
      `/api/constellation${qs ? `?${qs}` : ""}`,
      constellationSchema,
      undefined,
      10000,
      0,
    );
    const nodes: ConstellationNode[] = payload.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      kind: "artist" as const,
      weight: n.inLibrary ? 1.5 : 0.8,
      accent: n.inLibrary ? "#d4a03a" : undefined,
    }));
    const edges: ConstellationEdge[] = payload.edges.map((e) => ({
      id: `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      relationship: _mapConstellationRelationship(e.type),
      strength: e.weight ?? 0.5,
      reason: e.type,
    }));
    return { nodes, edges };
  } catch {
    // Fixture fallback — no error logged, constellation just shows mock data
    return { nodes: constellationNodes, edges: constellationEdges };
  }
}

export interface TasteProfile {
  dimensions: Record<string, number>;
  genreAffinity: Array<{ genre: string; score: number }>;
  eraDistribution: Record<string, number>;
  totalSignals: number;
  libraryStats: {
    totalTracks: number;
    scoredTracks: number;
    topArtists: Array<{ artist: string; count: number }>;
  };
}

export async function getTasteProfile(): Promise<TasteProfile> {
  const payload = await requestJson("/api/taste/profile", tasteProfileSchema, undefined, 8000, 0);
  return {
    dimensions: payload.dimensions,
    genreAffinity: payload.genre_affinity ?? [],
    eraDistribution: payload.era_distribution ?? {},
    totalSignals: payload.total_signals ?? 0,
    libraryStats: {
      totalTracks: payload.library_stats?.total_tracks ?? 0,
      scoredTracks: payload.library_stats?.scored_tracks ?? 0,
      topArtists: payload.library_stats?.top_artists ?? [],
    },
  };
}

export async function getFactDrop(trackId: string): Promise<AgentFactDrop> {
  const detail = await getTrackDossier(trackId);
  return { track_id: trackId, fact: detail.fact ?? null };
}

// ── Oracle Intelligence Queries ────────────────────────────────────────────

const playlustSchema = z.object({
  arc: z.string(),
  journey: z.array(z.record(z.any())),
  transition_avg: z.number().optional(),
  used_scores: z.boolean().optional(),
}).passthrough();

/**
 * Generate a Playlust — an emotionally sequenced listening journey.
 * Uses the arc engine to order tracks along a narrative trajectory.
 */
export async function generatePlaylust(
  prompt: string,
  arc: string = "slow_burn",
  n: number = 20,
): Promise<{ arc: string; journey: TrackListItem[]; transitionAvg: number }> {
  const payload = await requestJson("/api/playlust/generate", playlustSchema, {
    method: "POST",
    body: JSON.stringify({ prompt, arc, n }),
  }, 15000, 0);
  return {
    arc: payload.arc,
    journey: (payload.journey ?? []).map((t: Record<string, unknown>) => mapTrack(t)),
    transitionAvg: payload.transition_avg ?? 0,
  };
}

const deepCutSchema = z.object({
  results: z.array(z.record(z.any())),
  count: z.number().optional(),
}).passthrough();

/**
 * Hunt for deep cuts — acclaimed-but-obscure tracks aligned with taste.
 */
export async function getDeepCuts(limit: number = 20): Promise<TrackListItem[]> {
  const payload = await requestJson("/api/deep-cut/hunt", deepCutSchema, {
    method: "POST",
    body: JSON.stringify({ limit }),
  }, 10000, 0);
  return (payload.results ?? []).map((t: Record<string, unknown>) => mapTrack(t));
}

const crossGenreSchema = z.object({
  bridge_artists: z.array(z.record(z.any())).optional(),
  results: z.array(z.record(z.any())).optional(),
}).passthrough();

/**
 * Cross-genre discovery — find music that bridges two sonic worlds.
 */
export async function crossGenreDiscover(
  genre1: string,
  genre2: string,
  limit: number = 15,
): Promise<Array<{ artist: string; score: number; genres: string[] }>> {
  const payload = await requestJson("/api/scout/cross-genre", crossGenreSchema, {
    method: "POST",
    body: JSON.stringify({ genre1, genre2, limit }),
  }, 10000, 0);
  return (payload.bridge_artists ?? payload.results ?? []).map((r: Record<string, unknown>) => ({
    artist: String(r.artist ?? r.name ?? ""),
    score: Number(r.score ?? r.bridge_score ?? 0),
    genres: Array.isArray(r.genres) ? r.genres.map(String) : [],
  }));
}

/**
 * Trace artist lineage — discover influence chains, collaborations, rivalries.
 */
export async function traceArtistLineage(
  artist: string,
): Promise<{ connections: Array<{ target: string; type: string; weight: number }> }> {
  const schema = z.object({
    connections: z.array(z.object({
      target: z.string(),
      type: z.string(),
      weight: z.number().default(0.5),
    })).optional().default([]),
  }).passthrough();
  const payload = await requestJson("/api/lore/trace", schema, {
    method: "POST",
    body: JSON.stringify({ artist }),
  }, 10000, 0);
  return { connections: (payload.connections ?? []).map((c) => ({ target: c.target, type: c.type, weight: c.weight ?? 0.5 })) };
}

export async function getAgentSuggestion(_trackId?: string): Promise<AgentSuggestion> {
  try {
    return await requestJson("/api/agent/suggest", agentSuggestionSchema, undefined, 5000, 0);
  } catch {
    return { suggestion: "Use Oracle to pivot without losing the listening thread.", action: "open_oracle" };
  }
}

export async function queryAgent(text: string): Promise<{ action: string; thought: string; intent: Record<string, unknown>; next: string; response: string }> {
  try {
    const schema = z.object({
      action: z.string().optional().default("noop"),
      thought: z.string().optional().default(""),
      intent: z.record(z.any()).optional().default({}),
      next: z.string().optional().default(""),
      response: z.string().optional().default(""),
    }).passthrough();
    const result = await requestJson("/api/agent/query", schema, {
      method: "POST",
      body: JSON.stringify({ text }),
    }, 15000, 0);
    return {
      action: result.action ?? "noop",
      thought: result.thought ?? "",
      intent: result.intent ?? {},
      next: result.next ?? "",
      response: result.response ?? "",
    };
  } catch (error) {
    return {
      action: "error",
      thought: error instanceof Error ? error.message : "Agent unavailable",
      intent: {},
      next: "",
      response: error instanceof Error ? error.message : "The oracle could not process this request.",
    };
  }
}

// ── Oracle Discovery ────────────────────────────────────────────────────────

import type { OracleDiscoverySuggestion, OracleGap } from "@/types/domain";
import { oracleDiscoverySchema, oracleGapsSchema } from "@/config/schemas";

/**
 * Oracle Discovery — find music you don't have based on taste,
 * connections, scene, and cultural context.
 */
export async function getOracleDiscovery(
  limit: number = 30,
  seedArtist?: string,
): Promise<{ count: number; results: OracleDiscoverySuggestion[] }> {
  const body: Record<string, unknown> = { limit };
  if (seedArtist) body.seed_artist = seedArtist;
  const payload = await requestJson("/api/oracle/discover", oracleDiscoverySchema, {
    method: "POST",
    body: JSON.stringify(body),
  }, 20000, 0);
  return {
    count: payload.count,
    results: payload.results.map((r) => ({
      artist: r.artist,
      connectedFrom: r.connected_from,
      connectionType: r.connection_type,
      weight: r.weight,
      score: r.score,
      reasons: r.reasons,
      alreadyQueued: r.already_queued,
    })),
  };
}

/**
 * Queue oracle-discovered artists for acquisition.
 */
export async function queueOracleDiscoveries(
  tracks: Array<{ artist: string; title?: string; album?: string; score?: number }>,
): Promise<{ queued: number; total: number }> {
  const schema = z.object({ queued: z.number(), total: z.number() });
  return requestJson("/api/oracle/discover/queue", schema, {
    method: "POST",
    body: JSON.stringify({ tracks }),
  }, 10000, 0);
}

/**
 * Spotify gaps — tracks in the user's Spotify library never queued for acquisition.
 */
export async function getOracleGaps(limit: number = 100): Promise<OracleGap[]> {
  const payload = await requestJson(`/api/oracle/gaps?limit=${limit}`, oracleGapsSchema);
  return payload.results.map((r) => ({
    artist: r.artist,
    title: r.title,
    album: r.album ?? null,
    popularity: r.popularity ?? null,
    releaseDate: r.release_date ?? null,
    spotifyUri: r.spotify_uri ?? null,
  }));
}
