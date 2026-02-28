import { constellationEdges, constellationNodes, dossier, oracleRecommendations, playlistDetails, playlistSummaries, searchResults } from "@/mocks/fixtures/data";
import { fixtureModeEnabled } from "@/mocks/fixtures/mode";
import { agentSuggestionSchema, dossierSchema, healthSchema, libraryAlbumsSchema, libraryArtistsSchema, libraryTracksSchema, playlistDetailSchema, queueSchema, radioResultsSchema, searchSchema, vibesSchema } from "@/config/schemas";
import type {
  AgentFactDrop,
  AgentSuggestion,
  BootStatus,
  ConstellationEdge,
  ConstellationNode,
  OracleMode,
  OracleRecommendation,
  PlaylistDetail,
  PlaylistSummary,
  QueueState,
  SearchResultGroup,
  TrackDossier,
  TrackListItem,
} from "@/types/domain";
import { requestJson } from "./client";
import { mapBootStatus, mapDossier, mapOracleRecommendations, mapPlaylistDetail, mapPlaylists, mapRadioQueue, mapSearch, mapTrack } from "./mappers";
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
    const payload = await requestJson("/api/search", searchSchema, {
      method: "POST",
      body: JSON.stringify({ query, n: 12, rewrite_with_llm: true }),
    });
    return mapSearch(payload, playlists);
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, { ...searchResults, query });
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
