import { bootStatus, constellationEdges, constellationNodes, dossier, oracleRecommendations, playlistDetails, playlistSummaries, searchResults } from "@/mocks/fixtures/data";
import type {
  AgentFactDrop,
  AgentResponse,
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
} from "@/types/domain";
import { requestJson } from "./client";
import { mapBootStatus, mapDossier, mapPlaylistDetail, mapPlaylists, mapRadioQueue, mapSearch } from "./mappers";

async function withFallback<T>(work: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await work();
  } catch {
    return fallback;
  }
}

export async function getBootStatus(): Promise<BootStatus> {
  return withFallback(async () => mapBootStatus(await requestJson("/api/health")), bootStatus);
}

export async function getPlaylists(): Promise<PlaylistSummary[]> {
  return withFallback(async () => {
    const payload = await requestJson("/api/vibes");
    const mapped = mapPlaylists(payload);
    return mapped.length ? mapped : playlistSummaries;
  }, playlistSummaries);
}

export async function getPlaylistDetail(id: string): Promise<PlaylistDetail> {
  return withFallback(async () => {
    const playlists = await getPlaylists();
    const summary = playlists.find((item) => item.id === id) ?? playlistSummaries[0];
    const payload = await requestJson("/api/library/tracks?limit=12");
    return mapPlaylistDetail(summary, payload, oracleRecommendations);
  }, playlistDetails[id] ?? playlistDetails["after-midnight-ritual"]);
}

export async function getSearchResults(query: string): Promise<SearchResultGroup> {
  return withFallback(async () => {
    const playlists = await getPlaylists();
    const payload = await requestJson("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, n: 12, rewrite_with_llm: true }),
    });
    return mapSearch(payload, playlists, oracleRecommendations);
  }, { ...searchResults, query });
}

export async function getOracleRecommendations(mode: OracleMode): Promise<OracleRecommendation[]> {
  return withFallback(async () => {
    if (mode === "constellation") {
      return oracleRecommendations;
    }

    const path =
      mode === "flow"
        ? "/api/radio/flow"
        : mode === "discovery"
          ? "/api/radio/discovery?count=4"
          : "/api/radio/chaos";

    const payload: any =
      mode === "discovery"
        ? await requestJson(path)
        : await requestJson(path, {
            method: "POST",
            body: JSON.stringify({ count: 4 }),
          });

    const preview = Array.isArray(payload?.results) ? payload.results.slice(0, 4) : [];
    return [
      {
        id: `oracle-${mode}`,
        mode,
        title: `Oracle ${mode}`,
        rationale: `Live ${mode} signal translated into a listening move.`,
        confidenceLabel: "Live signal",
        seedLabel: "Current taste memory",
        previewTracks: preview.length ? preview.map((row: any) => mapSearch({ results: [row], query: "" }, [], []).tracks[0]) : oracleRecommendations[0].previewTracks,
        actions: ["play-now", "replace-queue", "append-queue", "open-constellation"],
      },
    ];
  }, oracleRecommendations.filter((item) => item.mode === mode || mode === "constellation"));
}

export async function getQueue(mode: OracleMode = "flow"): Promise<QueueState> {
  return withFallback(async () => {
    const payload = await requestJson("/api/radio/queue", {
      method: "POST",
      body: JSON.stringify({ mode, length: 12 }),
    });
    return mapRadioQueue(payload);
  }, {
    queueId: "fixture-queue",
    origin: mode,
    algorithm: mode,
    generatedAt: new Date().toISOString(),
    reorderable: true,
    currentIndex: 0,
    items: oracleRecommendations[0].previewTracks,
  });
}

export async function getTrackDossier(trackId: string): Promise<TrackDossier> {
  return withFallback(async () => {
    const detail = await getPlaylistDetail("after-midnight-ritual");
    const track = detail.tracks.find((item) => item.trackId === trackId) ?? detail.tracks[0];
    const [structurePayload, lorePayload, dnaPayload] = await Promise.all([
      requestJson(`/api/structure/${trackId}`),
      requestJson(`/api/lore/connections?artist=${encodeURIComponent(track.artist)}`),
      requestJson(`/api/dna/trace?track_id=${encodeURIComponent(trackId)}`),
    ]);
    return mapDossier(track, structurePayload, lorePayload, dnaPayload);
  }, dossier);
}

export async function getConstellation(): Promise<{ nodes: ConstellationNode[]; edges: ConstellationEdge[] }> {
  return { nodes: constellationNodes, edges: constellationEdges };
}

export async function queryAgent(text: string, context?: Record<string, unknown>, execute = false): Promise<AgentResponse> {
  return withFallback(
    () =>
      requestJson<AgentResponse>("/api/agent/query", {
        method: "POST",
        body: JSON.stringify({ text, context, execute }),
      }, 15_000),
    { action: "", thought: "The trail went cold, Boss.", intent: {}, next: "", response: "Agent unavailable." },
  );
}

export async function getFactDrop(trackId: string): Promise<AgentFactDrop> {
  return withFallback(
    () => requestJson<AgentFactDrop>(`/api/agent/fact-drop?track_id=${encodeURIComponent(trackId)}`),
    { track_id: trackId, fact: null },
  );
}

export async function getAgentSuggestion(trackId?: string): Promise<AgentSuggestion> {
  const qs = trackId ? `?track_id=${encodeURIComponent(trackId)}` : "";
  return withFallback(
    () => requestJson<AgentSuggestion>(`/api/agent/suggest${qs}`),
    { suggestion: "Feeling adventurous? Try chaos mode.", action: "chaos_mode" },
  );
}
