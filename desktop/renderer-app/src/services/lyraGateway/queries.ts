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
  searchSchema,
  tasteProfileSchema,
  vibeCreateSchema,
  vibeGenerateSchema,
  vibesSchema,
} from "@/config/schemas";
import type {
  AgentFactDrop,
  AgentResponse,
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
import { mapBootStatus, mapDoctorReport, mapDossier, mapGeneratedVibe, mapOracleRecommendations, mapPlaylistDetail, mapPlaylists, mapRadioQueue, mapSearch, mapTrack } from "./mappers";
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
    const playlistsPromise = getPlaylists().catch(() => []);
    const payload = await requestJson("/api/search", searchSchema, {
      method: "POST",
      body: JSON.stringify({ query, n: 20, natural_language: true }),
    });
    const playlists = await playlistsPromise;
    return mapSearch(payload, playlists);
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
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, { nodes: constellationNodes, edges: constellationEdges });
    }
    throw error;
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

// ── Agent Briefing ────────────────────────────────────────────────────────

export interface AgentBriefing {
  newest_tracks: Array<{ artist: string; title: string }>;
  taste_snapshot: Record<string, { value: number; confidence: number }>;
  top_queue_items: Array<{ artist: string; title: string; priority: number }>;
  playback_total: number;
  library_total: number;
}

export async function getAgentBriefing(): Promise<AgentBriefing> {
  try {
    const payload = await requestJson(
      "/api/agent/briefing",
      z.object({
        newest_tracks: z.array(z.object({ artist: z.string(), title: z.string() })).default([]),
        taste_snapshot: z.record(z.object({ value: z.number(), confidence: z.number() })).default({}),
        top_queue_items: z.array(z.object({ artist: z.string(), title: z.string(), priority: z.number() })).default([]),
        playback_total: z.number().default(0),
        library_total: z.number().default(0),
      }).passthrough(),
      undefined,
      5000,
      0,
    );
    return payload as AgentBriefing;
  } catch {
    return {
      newest_tracks: [],
      taste_snapshot: {},
      top_queue_items: [],
      playback_total: 0,
      library_total: 0,
    };
  }
}

export async function getFactDrop(trackId: string): Promise<AgentFactDrop> {
  const detail = await getTrackDossier(trackId);
  return { track_id: trackId, fact: detail.fact ?? null };
}

export async function getAgentSuggestion(_trackId?: string): Promise<AgentSuggestion> {
  try {
    return await requestJson("/api/agent/suggest", agentSuggestionSchema, undefined, 5000, 0);
  } catch {
    return { suggestion: "Use Oracle to pivot without losing the listening thread.", action: "open_oracle" };
  }
}

export async function queryAgent(text: string): Promise<AgentResponse> {
  try {
    const payload = await requestJson(
      "/api/agent/query",
      z.object({
        action: z.string().optional(),
        thought: z.string().optional(),
        intent: z.record(z.any()).optional(),
        next: z.union([z.string(), z.record(z.any())]).optional(),
        response: z.string().optional(),
      }).passthrough(),
      {
        method: "POST",
        body: JSON.stringify({ text, execute: false }),
      },
      10000,
      0,
    );
    return {
      action: typeof payload.action === "string" ? payload.action : "agent.query",
      thought: typeof payload.thought === "string" ? payload.thought : "Tracing intent...",
      intent: payload.intent && typeof payload.intent === "object" ? payload.intent as Record<string, unknown> : {},
      next: typeof payload.next === "string" ? payload.next : payload.next ?? "",
      response:
        typeof payload.response === "string" && payload.response.trim()
          ? payload.response
          : typeof payload.thought === "string"
            ? payload.thought
            : "Agent response received.",
    };
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, {
        action: "noop",
        thought: "Fixture mode active.",
        intent: {},
        next: "",
        response: "Agent execution is unavailable in fixture mode.",
      });
    }
    throw error;
  }
}
