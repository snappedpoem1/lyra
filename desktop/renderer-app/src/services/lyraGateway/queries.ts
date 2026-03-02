import { constellationEdges, constellationNodes, doctorChecks, dossier, oracleRecommendations, playlistDetails, playlistSummaries, searchResults } from "@/mocks/fixtures/data";
import { fixtureModeEnabled } from "@/mocks/fixtures/mode";import { z } from "zod";import { agentSuggestionSchema, doctorSchema, dossierSchema, healthSchema, libraryAlbumDetailSchema, libraryAlbumsSchema, libraryArtistDetailSchema, libraryArtistsSchema, libraryTracksSchema, playlistDetailSchema, queueSchema, radioResultsSchema, vibeCreateSchema, vibeGenerateSchema, vibesSchema } from "@/config/schemas";
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

export async function getConstellation(): Promise<{ nodes: ConstellationNode[]; edges: ConstellationEdge[] }> {
  return { nodes: constellationNodes, edges: constellationEdges };
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

export async function queryAgent(_text: string): Promise<{ action: string; thought: string; intent: Record<string, unknown>; next: string; response: string }> {
  return {
    action: "noop",
    thought: "Agent path is available through the backend, but the desktop command palette is currently read-only.",
    intent: {},
    next: "",
    response: "Agent execution is not wired in this rescue pass.",
  };
}
