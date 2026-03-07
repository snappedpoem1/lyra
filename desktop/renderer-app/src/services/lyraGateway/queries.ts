import { constellationEdges, constellationNodes, doctorChecks, dossier, oracleRecommendations, playlistDetails, playlistSummaries, searchResults } from "@/mocks/fixtures/data";
import { fixtureModeEnabled } from "@/mocks/fixtures/mode";
import { z } from "zod";
import {
  agentSuggestionSchema,
  artistShrineSchema,
  constellationSchema,
  deepCutHuntSchema,
  doctorSchema,
  dossierSchema,
  healthSchema,
  libraryAlbumDetailSchema,
  libraryAlbumsSchema,
  libraryArtistDetailSchema,
  libraryArtistsSchema,
  libraryTracksSchema,
  playlistDetailSchema,
  playlustGenerateSchema,
  queueSchema,
  radioResultsSchema,
  recommendationBrokerSchema,
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
  EvidenceItem,
  LibraryAlbumDetail,
  RecommendationAvailability,
  LibraryArtistDetail,
  OracleMode,
  OracleRecommendation,
  PlaylistDetail,
  PlaylistSummary,
  RecommendationBrokerResponse,
  RecommendationNoveltyBand,
  RecommendationProviderStatus,
  QueueState,
  SearchResultGroup,
  TrackDossier,
  TrackListItem,
  VibeCreateResult,
  VibeGenerateResult,
} from "@/types/domain";
import { requestJson, resolveApiUrl } from "./client";
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

export async function getSavedPlaylists(): Promise<Array<{ id: string; name: string; description: string; track_count: number; created_at: number; updated_at: number }>> {
  const res = await fetch(resolveApiUrl("/api/playlists"));
  if (!res.ok) throw new Error(`getSavedPlaylists failed: ${res.status}`);
  const data = await res.json() as { playlists: Array<{ id: string; name: string; description: string; track_count: number; created_at: number; updated_at: number }> };
  return data.playlists ?? [];
}

export async function createPlaylist(name: string, description = "", trackIds: string[] = []): Promise<{ id: string; name: string }> {
  const res = await fetch(resolveApiUrl("/api/playlists"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, track_ids: trackIds }),
  });
  if (!res.ok) throw new Error(`createPlaylist failed: ${res.status}`);
  const data = await res.json() as { playlist: { id: string; name: string } };
  return data.playlist;
}

export async function addTracksToPlaylist(playlistId: string, trackIds: string[]): Promise<void> {
  const res = await fetch(resolveApiUrl(`/api/playlists/${encodeURIComponent(playlistId)}/tracks`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_ids: trackIds }),
  });
  if (!res.ok) throw new Error(`addTracksToPlaylist failed: ${res.status}`);
}

export async function removeTrackFromPlaylist(playlistId: string, trackId: string): Promise<void> {
  const res = await fetch(resolveApiUrl(`/api/playlists/${encodeURIComponent(playlistId)}/tracks/${encodeURIComponent(trackId)}`), {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`removeTrackFromPlaylist failed: ${res.status}`);
}

export async function deletePlaylist(playlistId: string): Promise<void> {
  const res = await fetch(resolveApiUrl(`/api/playlists/${encodeURIComponent(playlistId)}`), {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`deletePlaylist failed: ${res.status}`);
}

export async function playPlaylist(playlistId: string): Promise<void> {
  const res = await fetch(resolveApiUrl(`/api/playlists/${encodeURIComponent(playlistId)}/play`), {
    method: "POST",
  });
  if (!res.ok) throw new Error(`playPlaylist failed: ${res.status}`);
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
      const queuePayload = await requestJson("/api/radio/queue", queueSchema, {
        method: "POST",
        body: JSON.stringify({ mode, length: 4, seed_track: seedTrackId }),
      });
      return [{
        id: "oracle-constellation",
        mode,
        title: "Oracle constellation pivots",
        rationale: "Live pivots from your current library graph and radio queue.",
        confidenceLabel: "Live graph",
        seedLabel: "Constellation",
        previewTracks: queuePayload.queue.map((row) => mapTrack(row)),
        actions: ["play-now", "replace-queue", "append-queue", "open-constellation"],
      }];
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

export async function getBrokeredRecommendations(options: {
  mode: OracleMode;
  seedTrackId?: string;
  noveltyBand?: RecommendationNoveltyBand;
  limit?: number;
  providerWeights?: Record<string, number>;
}): Promise<RecommendationBrokerResponse> {
  const payload = await requestJson("/api/recommendations/oracle", recommendationBrokerSchema, {
    method: "POST",
    body: JSON.stringify({
      mode: options.mode,
      seed_track_id: options.seedTrackId,
      novelty_band: options.noveltyBand ?? "stretch",
      limit: options.limit ?? 12,
      provider_weights: options.providerWeights ?? undefined,
    }),
  });

  const providerStatus = Object.fromEntries(
    Object.entries(payload.provider_status).map(([key, value]) => [
      key,
      {
        available: value.available,
        used: value.used,
        weight: value.weight,
        message: value.message,
        matchedLocalTracks: value.matched_local_tracks ?? 0,
        acquisitionCandidates: value.acquisition_candidates ?? 0,
      } satisfies RecommendationProviderStatus,
    ]),
  );

  const providerReports = Array.isArray(payload.provider_reports)
    ? payload.provider_reports.map((r) => ({
        provider: r.provider,
        status: r.status as "ok" | "empty" | "degraded" | "failed",
        message: r.message,
        seedContext: r.seed_context,
        candidates: r.candidates,
        errors: r.errors.map((e) => ({
          code: e.code,
          message: e.message,
          detail: e.detail,
        })),
        timingMs: r.timing_ms,
      }))
    : [];

  const mapEvidence = (raw: unknown[]): EvidenceItem[] =>
    raw.map((item) => item as Record<string, unknown>).map((e) => ({
      type: String(e.type ?? ""),
      source: String(e.source ?? ""),
      weight: typeof e.weight === "number" ? e.weight : 0,
      text: String(e.text ?? ""),
      rawValue: e.raw_value,
    }));

  return {
    schemaVersion: payload.schema_version,
    mode: payload.mode,
    noveltyBand: payload.novelty_band,
    seedTrackId: payload.seed_track_id ?? undefined,
    seedTrack: payload.seed_track ? mapTrack(payload.seed_track) : null,
    providerWeights: payload.provider_weights,
    providerStatus,
    providerReports,
    degraded: payload.degraded ?? false,
    degradationSummary: payload.degradation_summary ?? "",
    recommendations: payload.candidates.map((row) => ({
      track: mapTrack(row),
      brokerScore: typeof row.broker_score === "number" ? row.broker_score : Number(row.broker_score ?? 0),
      primaryReason: typeof row.reason === "string" ? row.reason : "Brokered recommendation",
      evidence: Array.isArray(row.evidence) ? mapEvidence(row.evidence) : [],
      confidence: typeof row.confidence === "number" ? row.confidence : 0,
      noveltyBandFit: typeof row.novelty_band_fit === "string" ? row.novelty_band_fit : "stretch",
      availability: (typeof row.availability === "string" ? row.availability : "unresolved") as RecommendationAvailability,
      explanation: typeof row.explanation === "string" ? row.explanation : "",
      explanationChips: Array.isArray(row.explanation_chips)
        ? row.explanation_chips.map((c: Record<string, unknown>) => ({
            label: String(c.label ?? ""),
            kind: String(c.kind ?? "reason") as import("@/types/domain").ExplanationChipKind,
          }))
        : [],
      providerSignals: Array.isArray(row.provider_signals)
        ? row.provider_signals.flatMap((signal: Record<string, unknown>) => {
            if (!signal || typeof signal !== "object") {
              return [];
            }
            return [{
              provider: String(signal.provider ?? "unknown"),
              label: String(signal.label ?? "signal"),
              score: typeof signal.score === "number" ? signal.score : Number(signal.score ?? 0),
              rawScore: typeof signal.raw_score === "number" ? signal.raw_score : Number(signal.raw_score ?? 0),
              reason: String(signal.reason ?? ""),
            }];
          })
        : [],
    })),
    acquisitionLeads: payload.acquisition_candidates.map((row) => ({
      artist: row.artist,
      title: row.title,
      provider: row.provider,
      reason: row.reason,
      score: row.score,
      evidence: Array.isArray(row.evidence) ? mapEvidence(row.evidence) : [],
    })),
    whatNext: Array.isArray(payload.what_next)
      ? payload.what_next.map((h) => ({
          track_id: h.track_id,
          artist: h.artist,
          title: h.title,
          hint: h.hint,
        }))
      : [],
  };
}

export async function submitRecommendationFeedback(payload: {
  feedbackType: "accepted" | "queued" | "skipped" | "replayed" | "acquire_requested" | "keep" | "play" | "dismiss";
  trackId?: string;
  artist?: string;
  title?: string;
  seedTrackId?: string;
  mode?: OracleMode;
  noveltyBand?: RecommendationNoveltyBand;
  provider?: string;
  metadata?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson("/api/recommendations/oracle/feedback", oracleActionResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      feedback_type: payload.feedbackType,
      track_id: payload.trackId,
      artist: payload.artist,
      title: payload.title,
      seed_track_id: payload.seedTrackId,
      mode: payload.mode,
      novelty_band: payload.noveltyBand,
      provider: payload.provider,
      metadata: payload.metadata,
    }),
  }) as Promise<Record<string, unknown>>;
}

export async function getFeedbackEffects(options?: {
  limit?: number;
  lookback?: number;
}): Promise<import("@/types/domain").FeedbackEffectsResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.lookback) params.set("lookback", String(options.lookback));
  const qs = params.toString();
  const url = `/api/recommendations/feedback-effects${qs ? `?${qs}` : ""}`;

  const feedbackEffectsSchema = z.object({
    effects: z.array(z.object({
      feedback_type: z.string(),
      artist: z.string(),
      title: z.string(),
      track_id: z.string(),
      effect: z.string(),
      created_at: z.number(),
    })),
    direction: z.object({
      direction: z.string(),
      summary: z.string(),
      signal_count: z.number(),
    }),
  });

  const payload = await requestJson(url, feedbackEffectsSchema);
  return payload;
}

export async function searchSemanticTracks(query: string, n = 20): Promise<TrackListItem[]> {
  const safeQuery = query.trim();
  if (!safeQuery) {
    return [];
  }
  try {
    const payload = await requestJson("/api/search", searchSchema, {
      method: "POST",
      body: JSON.stringify({ query: safeQuery, n, natural_language: true }),
    });
    return payload.results.map((row) => mapTrack(row));
  } catch (error) {
    if (fixtureModeEnabled()) {
      return useFixtureFallback(error, searchResults.tracks);
    }
    throw error;
  }
}

export interface DeepCutCandidate {
  track: TrackListItem;
  obscurityScore: number;
  acclaimScore: number;
  popularityPercentile: number;
  tags: string[];
}

export async function huntDeepCut(options: {
  genre?: string;
  artist?: string;
  minObscurity?: number;
  maxObscurity?: number;
  minAcclaim?: number;
  limit?: number;
} = {}): Promise<DeepCutCandidate[]> {
  const payload = await requestJson("/api/deep-cut/hunt", deepCutHuntSchema, {
    method: "POST",
    body: JSON.stringify({
      genre: options.genre,
      artist: options.artist,
      min_obscurity: options.minObscurity ?? 0.6,
      max_obscurity: options.maxObscurity ?? 2.0,
      min_acclaim: options.minAcclaim ?? 0.0,
      limit: options.limit ?? 20,
    }),
  });
  return payload.results.map((row) => ({
    track: mapTrack(row),
    obscurityScore: typeof row.obscurity_score === "number" ? row.obscurity_score : Number(row.obscurity_score ?? 0),
    acclaimScore: typeof row.acclaim_score === "number" ? row.acclaim_score : Number(row.acclaim_score ?? 0),
    popularityPercentile: typeof row.popularity_percentile === "number" ? row.popularity_percentile : Number(row.popularity_percentile ?? 0),
    tags: Array.isArray(row.tags) ? row.tags.map(String) : [],
  }));
}

export interface PlaylustArc {
  runUuid?: string;
  narrative?: string;
  tracks: TrackListItem[];
  acts: Array<{
    act: string;
    tracks: TrackListItem[];
  }>;
}

export async function generatePlaylustArc(options: {
  mood?: string;
  durationMinutes?: number;
  name?: string;
  useDeepcut?: boolean;
} = {}): Promise<PlaylustArc> {
  const payload = await requestJson("/api/playlust/generate", playlustGenerateSchema, {
    method: "POST",
    body: JSON.stringify({
      mood: options.mood,
      duration_minutes: options.durationMinutes ?? 60,
      name: options.name,
      use_deepcut: options.useDeepcut ?? true,
    }),
  });
  return {
    runUuid: payload.run_uuid,
    narrative: payload.narrative,
    tracks: Array.isArray(payload.tracks) ? payload.tracks.map((row) => mapTrack(row)) : [],
    acts: Array.isArray(payload.acts)
      ? payload.acts.map((act) => ({
          act: act.act,
          tracks: act.tracks.map((row) => mapTrack(row)),
        }))
      : [],
  };
}

const oracleActionResponseSchema = z.object({
  status: z.string().optional(),
  action_type: z.string().optional(),
}).passthrough();

const acquisitionStatusSchema = z.object({
  status: z.string().default("unknown"),
  available_tiers: z.number().default(0),
  total_tiers: z.number().default(0),
  tiers: z.record(z.object({
    available: z.boolean().optional(),
    description: z.string().optional(),
  }).passthrough()).default({}),
  checked_at: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
}).passthrough();

const statusSchema = z.object({
  status: z.string(),
  acquisition: acquisitionStatusSchema.optional(),
}).passthrough();

export interface AcquisitionBootstrapStatus {
  status: string;
  availableTiers: number;
  totalTiers: number;
  checkedAt: number | null;
  degradedTiers: string[];
  error?: string;
}

export async function getAcquisitionBootstrapStatus(): Promise<AcquisitionBootstrapStatus> {
  const payload = await requestJson("/api/status", statusSchema, undefined, 5000, 0);
  const acquisition = payload.acquisition;
  if (!acquisition) {
    return {
      status: "unavailable",
      availableTiers: 0,
      totalTiers: 0,
      checkedAt: null,
      degradedTiers: [],
    };
  }

  const tiers = acquisition.tiers ?? {};
  const degradedTiers = Object.entries(tiers)
    .filter(([, value]) => !value.available)
    .map(([key]) => key);

  return {
    status: acquisition.status ?? "unknown",
    availableTiers: acquisition.available_tiers ?? 0,
    totalTiers: acquisition.total_tiers ?? 0,
    checkedAt: acquisition.checked_at ?? null,
    degradedTiers,
    error: acquisition.error ?? undefined,
  };
}

export async function executeOracleAction(
  actionType: string,
  payload: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  return requestJson("/api/oracle/action/execute", oracleActionResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      action_type: actionType,
      payload,
    }),
  }) as Promise<Record<string, unknown>>;
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
      inLibrary: n.inLibrary ?? false,
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
