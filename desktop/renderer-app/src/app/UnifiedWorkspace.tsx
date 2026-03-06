import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Badge, Button, Group, NumberInput, SegmentedControl, Slider, TextInput } from "@mantine/core";
import {
  executeOracleAction,
  getAcquisitionBootstrapStatus,
  getArtistShrine,
  getBrokeredRecommendations,
  getLibraryTracks,
  getTrackDossier,
  huntDeepCut,
  searchSemanticTracks,
  submitRecommendationFeedback,
  type AcquisitionBootstrapStatus,
  type ArtistShrine,
  type DeepCutCandidate,
} from "@/services/lyraGateway/queries";
import { listenHostBootStatus } from "@/services/host/tauriHost";
import {
  getPlayerQueue,
  getPlayerState,
  listenPlayerEvents,
  mapPlayerQueueItems,
  mapPlayerTrack,
  playerNext,
  playerPause,
  playerPlay,
  playerPrevious,
  playerQueueAdd,
  playerQueueReorder,
  playerSeek,
  playerSetMode,
  type PlayerQueuePayload,
  type PlayerStatePayload,
} from "@/services/playerGateway";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { DIMENSIONS } from "@/types/dimensions";
import type {
  AcquisitionLead,
  BrokeredRecommendation,
  OracleMode,
  RecommendationNoveltyBand,
  RecommendationProviderStatus,
  TrackDossier,
  TrackListItem,
} from "@/types/domain";

const ORACLE_MODES: OracleMode[] = ["flow", "chaos", "discovery"];
const NOVELTY_BANDS: RecommendationNoveltyBand[] = ["safe", "stretch", "chaos"];
const PROVIDER_LABELS: Record<string, string> = {
  local: "Local",
  lastfm: "Last.fm",
  listenbrainz: "ListenBrainz",
};
const DEFAULT_LIBRARY_LIMIT = 64;

type LibraryMode = "library" | "semantic" | "discover";

const LIBRARY_MODE_OPTIONS: Array<{ label: string; value: LibraryMode }> = [
  { label: "Library", value: "library" },
  { label: "Semantic", value: "semantic" },
  { label: "Deep Cut", value: "discover" },
];

const ORACLE_MODE_OPTIONS: Array<{ label: string; value: OracleMode }> = ORACLE_MODES.map((mode) => ({
  label: mode[0].toUpperCase() + mode.slice(1),
  value: mode,
}));

const NOVELTY_MODE_OPTIONS: Array<{ label: string; value: RecommendationNoveltyBand }> = NOVELTY_BANDS.map((band) => ({
  label: band[0].toUpperCase() + band.slice(1),
  value: band,
}));

const CHAOS_INTENSITY_OPTIONS: Array<{ label: string; value: "low" | "medium" | "high" }> = [
  { label: "Low", value: "low" },
  { label: "Medium", value: "medium" },
  { label: "High", value: "high" },
];

function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) {
    return "0:00";
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function toPlaybackStatus(status: string): "idle" | "loading" | "playing" | "paused" | "ended" | "error" {
  if (status === "playing" || status === "paused" || status === "ended" || status === "error" || status === "loading") {
    return status;
  }
  return "idle";
}

function applyStateSnapshot(payload: PlayerStatePayload): void {
  const track = mapPlayerTrack(payload.current_track);
  const durationSec = payload.duration_ms > 0 ? payload.duration_ms / 1000 : 0;
  const currentTimeSec = payload.position_ms > 0 ? payload.position_ms / 1000 : 0;
  usePlayerStore.setState((prev) => ({
    ...prev,
    track,
    status: toPlaybackStatus(payload.status),
    currentTimeSec,
    durationSec,
    progress: durationSec > 0 ? Math.min(1, currentTimeSec / durationSec) : 0,
    volume: payload.volume,
    muted: payload.muted,
    shuffle: payload.shuffle,
    repeatMode: payload.repeat_mode,
  }));
}

function applyQueueSnapshot(payload: PlayerQueuePayload): void {
  useQueueStore.getState().replaceQueue({
    queueId: "backend-player",
    origin: "backend-player",
    reorderable: true,
    currentIndex: payload.current_index,
    items: mapPlayerQueueItems(payload),
  });
}

async function loadPlayerBootstrap(): Promise<void> {
  const [state, queue] = await Promise.all([getPlayerState(), getPlayerQueue()]);
  applyStateSnapshot(state);
  applyQueueSnapshot(queue);
}

export function UnifiedWorkspace() {
  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const queueIds = useMemo(() => queue.items.map((item) => item.trackId), [queue.items]);

  const [bootMessage, setBootMessage] = useState<string>("Booting Lyra backend...");
  const [backendReady, setBackendReady] = useState<boolean>(false);
  const [bootRetryBusy, setBootRetryBusy] = useState<boolean>(false);
  const [libraryMode, setLibraryMode] = useState<LibraryMode>("library");
  const [libraryQuery, setLibraryQuery] = useState<string>("");
  const [libraryTracks, setLibraryTracks] = useState<TrackListItem[]>([]);
  const [libraryLoading, setLibraryLoading] = useState<boolean>(true);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [semanticQuery, setSemanticQuery] = useState<string>("");
  const [semanticRows, setSemanticRows] = useState<TrackListItem[]>([]);
  const [discoverGenre, setDiscoverGenre] = useState<string>("");
  const [discoverRows, setDiscoverRows] = useState<DeepCutCandidate[]>([]);
  const [searchBusy, setSearchBusy] = useState<boolean>(false);
  const [searchMessage, setSearchMessage] = useState<string>("");
  const [transportBusy, setTransportBusy] = useState<boolean>(false);
  const [oracleBusy, setOracleBusy] = useState<boolean>(false);
  const [oracleOpen, setOracleOpen] = useState<boolean>(true);
  const [controlDeckOpen, setControlDeckOpen] = useState<boolean>(false);
  const [oracleMode, setOracleMode] = useState<OracleMode>("flow");
  const [oracleNoveltyBand, setOracleNoveltyBand] = useState<RecommendationNoveltyBand>("stretch");
  const [chaosIntensity, setChaosIntensity] = useState<"low" | "medium" | "high">("medium");
  const [providerWeights, setProviderWeights] = useState<Record<string, number>>({
    local: 0.55,
    lastfm: 0.2,
    listenbrainz: 0.25,
  });
  const [brokerRecommendations, setBrokerRecommendations] = useState<BrokeredRecommendation[]>([]);
  const [acquisitionLeads, setAcquisitionLeads] = useState<AcquisitionLead[]>([]);
  const [providerStatus, setProviderStatus] = useState<Record<string, RecommendationProviderStatus>>({});
  const [oracleResultMessage, setOracleResultMessage] = useState<string>("");
  const [vibePrompt, setVibePrompt] = useState<string>("");
  const [playlustMood, setPlaylustMood] = useState<string>("");
  const [playlustMinutes, setPlaylustMinutes] = useState<number>(60);
  const [dossier, setDossier] = useState<TrackDossier | null>(null);
  const [artistIntel, setArtistIntel] = useState<ArtistShrine | null>(null);
  const [acquisitionStatus, setAcquisitionStatus] = useState<AcquisitionBootstrapStatus | null>(null);

  const currentTrack = player.track ?? queue.items[queue.currentIndex] ?? null;
  const safeDuration = Math.max(0, player.durationSec || currentTrack?.durationSec || 0);
  const safeProgressPct = safeDuration > 0 ? Math.min(100, (player.currentTimeSec / safeDuration) * 100) : 0;
  const uiLocked = !backendReady;
  const acquisitionSummary = useMemo(() => {
    if (!acquisitionStatus) {
      return "";
    }
    const base = `Acquisition tiers ${acquisitionStatus.availableTiers}/${acquisitionStatus.totalTiers} ready`;
    if (acquisitionStatus.degradedTiers.length > 0) {
      return `${base} | degraded: ${acquisitionStatus.degradedTiers.join(", ")}`;
    }
    return base;
  }, [acquisitionStatus]);
  const providerStatusSummary = useMemo(
    () =>
      Object.entries(providerStatus).map(([key, value]) => ({
        key,
        label: PROVIDER_LABELS[key] ?? key,
        status: value.available ? "online" : "offline",
        detail: value.message,
        weightPct: Math.round(value.weight * 100),
      })),
    [providerStatus],
  );

  const removeBrokerRecommendation = useCallback((trackId: string): void => {
    setBrokerRecommendations((current) => current.filter((item) => item.track.trackId !== trackId));
  }, []);

  const removeAcquisitionLead = useCallback((lead: AcquisitionLead): void => {
    setAcquisitionLeads((current) =>
      current.filter(
        (item) =>
          !(
            item.artist === lead.artist &&
            item.title === lead.title &&
            item.provider === lead.provider
          ),
      ),
    );
  }, []);

  const updateProviderWeight = useCallback((provider: string, nextValue: number): void => {
    setProviderWeights((current) => ({
      ...current,
      [provider]: Math.max(0, Math.min(1, nextValue)),
    }));
  }, []);

  const refreshBootstrap = useCallback(async (interactiveRetry = false): Promise<void> => {
    if (interactiveRetry) {
      setBootRetryBusy(true);
      setBootMessage("Retrying backend connection...");
    }
    try {
      await loadPlayerBootstrap();
      try {
        const status = await getAcquisitionBootstrapStatus();
        setAcquisitionStatus(status);
      } catch {
        setAcquisitionStatus(null);
      }
      setBackendReady(true);
      setBootMessage("Lyra backend connected");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to connect backend player";
      setBackendReady(false);
      setBootMessage(message);
      usePlayerStore.getState().setError(message);
    } finally {
      if (interactiveRetry) {
        setBootRetryBusy(false);
      }
    }
  }, []);

  const queueTrackIds = useCallback(
    async (trackIds: string[], message: string): Promise<void> => {
      const ids = Array.from(new Set(trackIds.filter((id) => id.trim().length > 0)));
      if (ids.length === 0) {
        setOracleResultMessage("No tracks available to queue.");
        return;
      }
      const actionResult = await executeOracleAction("queue_tracks", { track_ids: ids });
      const queuedCount = Number(actionResult["queued_count"] ?? ids.length);
      setOracleResultMessage(`${message} (${queuedCount} queued)`);
      await refreshBootstrap(false);
    },
    [refreshBootstrap],
  );

  const recordBrokerFeedback = useCallback(
    async (payload: {
      feedbackType: "accepted" | "queued" | "skipped" | "replayed" | "acquire_requested";
      trackId?: string;
      artist?: string;
      title?: string;
      provider?: string;
      metadata?: Record<string, unknown>;
    }): Promise<void> => {
      await submitRecommendationFeedback({
        feedbackType: payload.feedbackType,
        trackId: payload.trackId,
        artist: payload.artist,
        title: payload.title,
        provider: payload.provider,
        metadata: payload.metadata,
        seedTrackId: currentTrack?.trackId,
        mode: oracleMode,
        noveltyBand: oracleNoveltyBand,
      });
    },
    [currentTrack?.trackId, oracleMode, oracleNoveltyBand],
  );

  useEffect(() => {
    let active = true;
    void refreshBootstrap(false);
    const stopEvents = listenPlayerEvents(
      (event) => {
        if (!active) return;
        if (event.state) applyStateSnapshot(event.state);
        if (event.queue) applyQueueSnapshot(event.queue);
        if (event.error?.message) usePlayerStore.getState().setError(event.error.message);
      },
      (message) => {
        if (active) usePlayerStore.getState().setError(message);
      },
    );
    let stopHost: () => void = () => {};
    void (async () => {
      stopHost = await listenHostBootStatus((payload) => {
        if (!active || payload.phase !== "backend") return;
        setBootMessage(payload.message);
        setBackendReady(payload.ready);
      });
    })();
    const poll = window.setInterval(() => void refreshBootstrap(false), 15000);
    return () => {
      active = false;
      window.clearInterval(poll);
      stopEvents();
      stopHost();
    };
  }, [refreshBootstrap]);

  useEffect(() => {
    let cancelled = false;
    if (uiLocked) {
      setLibraryLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLibraryLoading(true);
    setLibraryError(null);
    const timer = window.setTimeout(() => {
      void getLibraryTracks(DEFAULT_LIBRARY_LIMIT, 0, libraryQuery.trim())
        .then((result) => {
          if (!cancelled) setLibraryTracks(result.tracks);
        })
        .catch((error) => {
          if (!cancelled) setLibraryError(error instanceof Error ? error.message : "Failed to load library");
        })
        .finally(() => {
          if (!cancelled) setLibraryLoading(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [libraryQuery, uiLocked]);

  useEffect(() => {
    let cancelled = false;
    if (uiLocked || !currentTrack?.trackId) {
      setDossier(null);
      setArtistIntel(null);
      return () => {
        cancelled = true;
      };
    }
    void getTrackDossier(currentTrack.trackId).then((payload) => {
      if (!cancelled) setDossier(payload);
    }).catch(() => {});
    void getArtistShrine(currentTrack.artist).then((payload) => {
      if (!cancelled) setArtistIntel(payload);
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentTrack?.artist, currentTrack?.trackId, uiLocked]);

  const transportAction = async (action: "play-pause" | "next" | "previous"): Promise<void> => {
    if (uiLocked || transportBusy) return;
    setTransportBusy(true);
    try {
      if (action === "play-pause") {
        if (player.status === "playing") applyStateSnapshot(await playerPause());
        else if (currentTrack?.trackId) applyStateSnapshot(await playerPlay({ track_id: currentTrack.trackId }));
        else if (queue.items.length > 0) applyStateSnapshot(await playerPlay({ queue_index: queue.currentIndex }));
        return;
      }
      if (action === "next") applyStateSnapshot(await playerNext());
      else applyStateSnapshot(await playerPrevious());
    } catch (error) {
      usePlayerStore.getState().setError(error instanceof Error ? error.message : "Transport failed");
    } finally {
      setTransportBusy(false);
    }
  };

  const playTrack = async (track: TrackListItem): Promise<void> => {
    if (uiLocked || !track.trackId) return;
    try {
      applyQueueSnapshot(await playerQueueAdd(track.trackId));
      applyStateSnapshot(await playerPlay({ track_id: track.trackId }));
    } catch (error) {
      usePlayerStore.getState().setError(error instanceof Error ? error.message : "Failed to play track");
    }
  };

  const moveQueueItem = async (index: number, direction: -1 | 1): Promise<void> => {
    if (uiLocked) return;
    const target = index + direction;
    if (target < 0 || target >= queueIds.length) return;
    const nextOrder = [...queueIds];
    const [moved] = nextOrder.splice(index, 1);
    nextOrder.splice(target, 0, moved);
    try {
      applyQueueSnapshot(await playerQueueReorder(nextOrder));
    } catch (error) {
      usePlayerStore.getState().setError(error instanceof Error ? error.message : "Failed to reorder queue");
    }
  };

  const onSeek = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    if (uiLocked || safeDuration <= 0) return;
    const pct = Number(event.target.value);
    if (!Number.isFinite(pct)) return;
    const targetMs = Math.max(0, Math.min(1, pct / 100)) * safeDuration * 1000;
    try {
      applyStateSnapshot(await playerSeek(Math.round(targetMs)));
    } catch (error) {
      usePlayerStore.getState().setError(error instanceof Error ? error.message : "Seek failed");
    }
  };

  const setPlayerMode = async (payload: { shuffle?: boolean; repeat_mode?: "off" | "one" | "all" }): Promise<void> => {
    if (uiLocked) return;
    try {
      applyStateSnapshot(await playerSetMode(payload));
    } catch (error) {
      usePlayerStore.getState().setError(error instanceof Error ? error.message : "Mode update failed");
    }
  };

  const runSemantic = async (): Promise<void> => {
    if (uiLocked || searchBusy) return;
    const query = semanticQuery.trim();
    if (!query) {
      setSearchMessage("Enter a semantic query.");
      return;
    }
    setSearchBusy(true);
    try {
      const rows = await searchSemanticTracks(query, 24);
      setSemanticRows(rows);
      setSearchMessage(rows.length ? `Found ${rows.length} matches.` : "No semantic matches.");
      setLibraryMode("semantic");
    } catch (error) {
      setSearchMessage(error instanceof Error ? error.message : "Semantic search failed");
    } finally {
      setSearchBusy(false);
    }
  };

  const runDeepCut = async (): Promise<void> => {
    if (uiLocked || searchBusy) return;
    setSearchBusy(true);
    try {
      const rows = await huntDeepCut({ genre: discoverGenre.trim() || undefined, limit: 20, minObscurity: 0.65, maxObscurity: 2.4, minAcclaim: 0.15 });
      setDiscoverRows(rows);
      setSearchMessage(rows.length ? `Deep Cut found ${rows.length} tracks.` : "No deep cuts for this filter.");
      setLibraryMode("discover");
    } catch (error) {
      setSearchMessage(error instanceof Error ? error.message : "Deep Cut hunt failed");
    } finally {
      setSearchBusy(false);
    }
  };

  const loadBrokerPreview = useCallback(async (): Promise<BrokeredRecommendation[]> => {
    const broker = await getBrokeredRecommendations({
      mode: oracleMode,
      seedTrackId: currentTrack?.trackId,
      noveltyBand: oracleNoveltyBand,
      limit: 12,
      providerWeights,
    });
    setBrokerRecommendations(broker.recommendations);
    setAcquisitionLeads(broker.acquisitionLeads);
    setProviderStatus(broker.providerStatus);
    if (broker.recommendations.length > 0) {
      setOracleResultMessage(`Broker revealed ${broker.recommendations.length} local recommendations.`);
    } else if (broker.acquisitionLeads.length > 0) {
      setOracleResultMessage(`No local matches yet. ${broker.acquisitionLeads.length} acquisition leads are ready.`);
    } else {
      setOracleResultMessage("No brokered recommendations were available for this thread.");
    }
    return broker.recommendations;
  }, [currentTrack?.trackId, oracleMode, oracleNoveltyBand, providerWeights]);

  const revealOraclePicks = async (): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await loadBrokerPreview();
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Broker preview failed");
    } finally {
      setOracleBusy(false);
    }
  };

  const submitOraclePicks = useCallback(async (): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      if (oracleMode === "chaos") {
        const action = await executeOracleAction("switch_chaos_intensity", { intensity: chaosIntensity, queue_now: true });
        setOracleResultMessage(`Chaos queued ${Number(action["queued_count"] ?? 0)} tracks.`);
        await refreshBootstrap(false);
        return;
      }
      const recommendations = await loadBrokerPreview();
      const queuedRecommendations = recommendations.slice(0, 12);
      await queueTrackIds(
        queuedRecommendations.map((item) => item.track.trackId),
        "Oracle queued broker recommendations",
      );
      await Promise.all(
        queuedRecommendations.map((item) =>
          recordBrokerFeedback({
            feedbackType: "queued",
            trackId: item.track.trackId,
            artist: item.track.artist,
            title: item.track.title,
            provider: item.providerSignals[0]?.provider ? String(item.providerSignals[0].provider) : "broker",
            metadata: { brokerScore: item.brokerScore, source: "bulk_queue" },
          }),
        ),
      );
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Oracle action failed");
    } finally {
      setOracleBusy(false);
    }
  }, [chaosIntensity, loadBrokerPreview, oracleBusy, oracleMode, queueTrackIds, recordBrokerFeedback, refreshBootstrap, uiLocked]);

  const submitStartVibe = async (): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    const prompt = vibePrompt.trim();
    if (!prompt) {
      setOracleResultMessage("Enter a vibe prompt first.");
      return;
    }
    setOracleBusy(true);
    try {
      const action = await executeOracleAction("start_vibe", { prompt, n: 30 });
      setOracleResultMessage(`Vibe queued ${Number(action["queued_count"] ?? 0)} tracks.`);
      await refreshBootstrap(false);
      setVibePrompt("");
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Vibe launch failed");
    } finally {
      setOracleBusy(false);
    }
  };

  const submitPlaylust = async (): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    const minutes = Math.max(10, Math.min(240, Math.round(playlustMinutes)));
    setOracleBusy(true);
    try {
      const action = await executeOracleAction("start_playlust", { mood: playlustMood.trim() || undefined, duration_minutes: minutes, use_deepcut: true });
      setOracleResultMessage(`Playlust queued ${Number(action["queued_count"] ?? 0)} tracks.`);
      await refreshBootstrap(false);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Playlust launch failed");
    } finally {
      setOracleBusy(false);
    }
  };

  const keepBrokerRecommendation = async (item: BrokeredRecommendation): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await recordBrokerFeedback({
        feedbackType: "accepted",
        trackId: item.track.trackId,
        artist: item.track.artist,
        title: item.track.title,
        provider: item.providerSignals[0]?.provider ? String(item.providerSignals[0].provider) : "broker",
        metadata: { brokerScore: item.brokerScore, action: "keep" },
      });
      removeBrokerRecommendation(item.track.trackId);
      setOracleResultMessage(`Stored ${item.track.artist} - ${item.track.title} as a strong oracle signal.`);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to save recommendation feedback");
    } finally {
      setOracleBusy(false);
    }
  };

  const skipBrokerRecommendation = async (item: BrokeredRecommendation): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await recordBrokerFeedback({
        feedbackType: "skipped",
        trackId: item.track.trackId,
        artist: item.track.artist,
        title: item.track.title,
        provider: item.providerSignals[0]?.provider ? String(item.providerSignals[0].provider) : "broker",
        metadata: { brokerScore: item.brokerScore, action: "skip" },
      });
      removeBrokerRecommendation(item.track.trackId);
      setOracleResultMessage(`Skipped ${item.track.artist} - ${item.track.title}. Future picks will adapt.`);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to save skip feedback");
    } finally {
      setOracleBusy(false);
    }
  };

  const queueBrokerRecommendation = async (item: BrokeredRecommendation): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await queueTrackIds([item.track.trackId], "Broker track queued");
      await recordBrokerFeedback({
        feedbackType: "queued",
        trackId: item.track.trackId,
        artist: item.track.artist,
        title: item.track.title,
        provider: item.providerSignals[0]?.provider ? String(item.providerSignals[0].provider) : "broker",
        metadata: { brokerScore: item.brokerScore, action: "queue" },
      });
      removeBrokerRecommendation(item.track.trackId);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to queue broker recommendation");
    } finally {
      setOracleBusy(false);
    }
  };

  const replayBrokerRecommendation = async (item: BrokeredRecommendation): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await playTrack(item.track);
      await recordBrokerFeedback({
        feedbackType: "replayed",
        trackId: item.track.trackId,
        artist: item.track.artist,
        title: item.track.title,
        provider: item.providerSignals[0]?.provider ? String(item.providerSignals[0].provider) : "broker",
        metadata: { brokerScore: item.brokerScore, action: "replay" },
      });
      removeBrokerRecommendation(item.track.trackId);
      setOracleResultMessage(`Replaying ${item.track.artist} - ${item.track.title}.`);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to replay broker recommendation");
    } finally {
      setOracleBusy(false);
    }
  };

  const requestAcquisitionLead = async (lead: AcquisitionLead): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      const action = await executeOracleAction("request_acquisition", {
        artist: lead.artist,
        title: lead.title,
        provider: lead.provider,
        reason: lead.reason,
        score: lead.score,
      });
      await recordBrokerFeedback({
        feedbackType: "acquire_requested",
        artist: lead.artist,
        title: lead.title,
        provider: String(lead.provider),
        metadata: { score: lead.score, actionStatus: action.status ?? "queued" },
      });
      removeAcquisitionLead(lead);
      setOracleResultMessage(`${lead.artist} - ${lead.title}: ${String(action.status ?? "queued")}.`);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to request acquisition");
    } finally {
      setOracleBusy(false);
    }
  };

  const dismissAcquisitionLead = async (lead: AcquisitionLead): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      await recordBrokerFeedback({
        feedbackType: "skipped",
        artist: lead.artist,
        title: lead.title,
        provider: String(lead.provider),
        metadata: { score: lead.score, action: "dismiss_lead" },
      });
      removeAcquisitionLead(lead);
      setOracleResultMessage(`Dismissed acquisition lead for ${lead.artist} - ${lead.title}.`);
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Failed to dismiss acquisition lead");
    } finally {
      setOracleBusy(false);
    }
  };

  const dimensionRows = DIMENSIONS.map((key) => ({ key, value: dossier?.scores[key] ?? null }));

  return (
    <div className={`unified-shell ${uiLocked ? "is-locked" : ""}`}>
      <header className="unified-header">
        <div>
          <div className="unified-brand">Lyra</div>
          <div className="unified-tag">music oracle entity</div>
        </div>
        <div className="header-actions">
          <Button variant="default" className="lyra-button" disabled={uiLocked} onClick={() => setControlDeckOpen((open) => !open)}>
            {controlDeckOpen ? "Hide Deck" : "Control Deck"}
          </Button>
          <div className="unified-boot">{bootMessage}</div>
        </div>
      </header>

      <section className="unified-grid" aria-busy={uiLocked}>
        <aside className="unified-pane library-pane">
          <div className="pane-head">
            <h2>Library</h2>
            {libraryMode === "library" && (
              <TextInput
                className="pane-input"
                placeholder="Search artist, title, album"
                value={libraryQuery}
                disabled={uiLocked}
                onChange={(event) => setLibraryQuery(event.target.value)}
                size="xs"
              />
            )}
          </div>

          <div className="unified-tabs">
            <SegmentedControl
              fullWidth
              data={LIBRARY_MODE_OPTIONS}
              value={libraryMode}
              onChange={(value) => setLibraryMode(value as LibraryMode)}
              disabled={uiLocked}
              size="xs"
            />
          </div>

          {libraryMode === "semantic" && (
            <Group className="search-strip" align="end">
              <TextInput
                className="pane-input"
                placeholder="late-night analog dub with tension"
                value={semanticQuery}
                disabled={uiLocked || searchBusy}
                onChange={(event) => setSemanticQuery(event.target.value)}
                size="xs"
                styles={{ root: { flex: 1 } }}
              />
              <Button variant="filled" color="lyra" className="lyra-button lyra-button--accent" disabled={uiLocked || searchBusy} onClick={() => void runSemantic()}>
                {searchBusy ? "Searching..." : "Search"}
              </Button>
              <Button
                className="lyra-button"
                disabled={uiLocked || semanticRows.length === 0}
                onClick={() => {
                  void queueTrackIds(semanticRows.slice(0, 10).map((row) => row.trackId), "Semantic set queued");
                }}
                variant="default"
              >
                Queue Top
              </Button>
            </Group>
          )}

          {libraryMode === "discover" && (
            <Group className="search-strip" align="end">
              <TextInput
                className="pane-input"
                placeholder="genre (optional): shoegaze"
                value={discoverGenre}
                disabled={uiLocked || searchBusy}
                onChange={(event) => setDiscoverGenre(event.target.value)}
                size="xs"
                styles={{ root: { flex: 1 } }}
              />
              <Button variant="filled" color="lyra" className="lyra-button lyra-button--accent" disabled={uiLocked || searchBusy} onClick={() => void runDeepCut()}>
                {searchBusy ? "Hunting..." : "Hunt"}
              </Button>
              <Button
                className="lyra-button"
                disabled={uiLocked || discoverRows.length === 0}
                onClick={() => {
                  void queueTrackIds(discoverRows.slice(0, 10).map((row) => row.track.trackId), "Deep Cut set queued");
                }}
                variant="default"
              >
                Queue Top
              </Button>
            </Group>
          )}

          <div className="pane-scroll">
            {searchMessage && libraryMode !== "library" && <div className="pane-meta">{searchMessage}</div>}
            {libraryMode === "library" && (
              <>
                {libraryLoading && <div className="pane-meta">Loading library...</div>}
                {libraryError && <div className="pane-error">{libraryError}</div>}
                {!libraryLoading && !libraryError && libraryTracks.length === 0 && <div className="pane-meta">No tracks found.</div>}
                {!libraryLoading && libraryTracks.map((track) => (
                  <button key={track.trackId} className="list-row" disabled={uiLocked} onClick={() => void playTrack(track)}>
                    <span className="list-title">{track.title}</span>
                    <span className="list-meta">{track.artist}</span>
                  </button>
                ))}
              </>
            )}

            {libraryMode === "semantic" && semanticRows.map((track) => (
              <button key={track.trackId} className="list-row" disabled={uiLocked} onClick={() => void playTrack(track)}>
                <span className="list-title">{track.title}</span>
                <span className="list-meta">{track.artist}</span>
              </button>
            ))}

            {libraryMode === "discover" && discoverRows.map((row) => (
              <div key={row.track.trackId} className="list-row list-row--discover">
                <button className="list-row-discover-main" disabled={uiLocked} onClick={() => void playTrack(row.track)}>
                  <span className="list-title">{row.track.title}</span>
                  <span className="list-meta">{row.track.artist}</span>
                  <span className="discover-meta">Obscurity {row.obscurityScore.toFixed(2)} | Acclaim {row.acclaimScore.toFixed(2)}</span>
                </button>
                <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => void queueTrackIds([row.track.trackId], "Deep Cut track queued")}>Queue</Button>
              </div>
            ))}
          </div>
        </aside>

        <main className="unified-pane now-pane">
          <div className="pane-head">
            <h2>Now Playing</h2>
            <div className="pane-meta">{player.status.toUpperCase()} | {queue.items.length ? `${queue.items.length} in queue` : "No queue"}</div>
          </div>
          <div className="now-track">
            <div className="now-title">{currentTrack?.title ?? "Nothing loaded"}</div>
            <div className="now-subtitle">{currentTrack?.artist ?? "Pick a track from library, semantic, deep cut, or oracle."}</div>
            <div className="now-album">{currentTrack?.album ?? ""}</div>
          </div>
          <div className="transport-row">
            <Button className="lyra-button" variant="default" disabled={uiLocked || transportBusy} onClick={() => void transportAction("previous")}>Previous</Button>
            <Button className="lyra-button lyra-button--accent" variant="filled" color="lyra" disabled={uiLocked || transportBusy} onClick={() => void transportAction("play-pause")}>{player.status === "playing" ? "Pause" : "Play"}</Button>
            <Button className="lyra-button" variant="default" disabled={uiLocked || transportBusy} onClick={() => void transportAction("next")}>Next</Button>
          </div>
          <div className="seek-row">
            <span>{fmtTime(player.currentTimeSec)}</span>
            <input disabled={uiLocked} type="range" min={0} max={100} value={safeProgressPct} onChange={(event) => void onSeek(event)} />
            <span>{fmtTime(safeDuration)}</span>
          </div>
          <div className="mode-row">
            <Button className={`lyra-button ${player.shuffle ? "lyra-button--accent" : ""}`} variant={player.shuffle ? "filled" : "default"} color="lyra" disabled={uiLocked} onClick={() => void setPlayerMode({ shuffle: !player.shuffle })}>Shuffle {player.shuffle ? "On" : "Off"}</Button>
            <SegmentedControl
              data={[
                { label: "Repeat Off", value: "off" },
                { label: "Repeat One", value: "one" },
                { label: "Repeat All", value: "all" },
              ]}
              value={player.repeatMode}
              disabled={uiLocked}
              onChange={(value) => void setPlayerMode({ repeat_mode: value as "off" | "one" | "all" })}
              size="xs"
            />
          </div>

          <div className="now-intel-grid">
            <section className="intel-card">
              <h3>Dimensional Profile</h3>
              <div className="dimension-grid">
                {dimensionRows.map((row) => (
                  <div key={row.key} className="dimension-row">
                    <span>{row.key}</span>
                    <div className="dimension-meter">
                      <div className="dimension-meter-fill" style={{ width: `${Math.max(0, Math.min(100, Math.round((row.value ?? 0) * 100)))}%` }} />
                    </div>
                    <span>{Math.max(0, Math.min(100, Math.round((row.value ?? 0) * 100)))}%</span>
                  </div>
                ))}
              </div>
            </section>
            <section className="intel-card">
              <h3>Lyrics + Notes</h3>
              {dossier?.lyrics?.excerpt ? <p className="lyrics-excerpt">{dossier.lyrics.excerpt}</p> : <p className="pane-meta">No cached lyrics context for this track yet.</p>}
              {dossier?.fact && <p className="fact-drop">{dossier.fact}</p>}
            </section>
          </div>
        </main>

        <aside className="unified-pane queue-pane">
          <div className="pane-head"><h2>Queue</h2></div>
          <div className="pane-scroll">
            {queue.items.length === 0 && <div className="pane-meta">Queue is empty.</div>}
            {queue.items.map((track, index) => (
              <div key={`${track.trackId}-${index}`} className={`queue-row-lite ${index === queue.currentIndex ? "is-current" : ""}`}>
                <div className="queue-row-lite-main">
                  <span className="list-title">{track.title}</span>
                  <span className="list-meta">{track.artist}</span>
                </div>
                <div className="queue-row-lite-actions">
                  <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => void moveQueueItem(index, -1)}>Up</Button>
                  <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => void moveQueueItem(index, 1)}>Down</Button>
                  <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => void playerPlay({ queue_index: index }).then((snapshot) => applyStateSnapshot(snapshot)).catch(() => {})}>Play</Button>
                </div>
              </div>
            ))}
          </div>
          <section className="artist-sidebar">
            <div className="pane-head"><h2>Artist Context</h2></div>
            {!artistIntel && <div className="pane-meta">No artist selected.</div>}
            {artistIntel && (
              <div className="artist-sidebar-content">
                <div className="artist-sidebar-name">{artistIntel.artist}</div>
                {artistIntel.origin && <div className="pane-meta">Origin: {artistIntel.origin}</div>}
                {artistIntel.genres.length > 0 && <div className="tag-row">{artistIntel.genres.slice(0, 6).map((genre) => <Badge key={genre} className="tag-chip" color="lyra">{genre}</Badge>)}</div>}
                {artistIntel.bio && <p className="artist-bio-lite">{artistIntel.bio}</p>}
              </div>
            )}
          </section>
        </aside>
      </section>

      <section className={`oracle-pane ${oracleOpen ? "is-open" : "is-collapsed"}`}>
        <div className="pane-head">
          <h2>Oracle</h2>
          <div className="header-actions">
            <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => setControlDeckOpen((open) => !open)}>
              {controlDeckOpen ? "Hide Deck" : "Control Deck"}
            </Button>
            <Button className="lyra-button" variant="default" disabled={uiLocked} onClick={() => setOracleOpen((open) => !open)}>{oracleOpen ? "Collapse" : "Expand"}</Button>
          </div>
        </div>
        {oracleOpen && (
          <>
            {controlDeckOpen && (
              <section className="control-deck">
                <div className="control-deck-row">
                  <span className="pane-meta">Novelty Band</span>
                  <SegmentedControl
                    data={NOVELTY_MODE_OPTIONS}
                    value={oracleNoveltyBand}
                    onChange={(value) => setOracleNoveltyBand(value as RecommendationNoveltyBand)}
                    disabled={uiLocked || oracleBusy}
                    size="xs"
                    fullWidth
                  />
                </div>
                <div className="control-deck-grid">
                  {Object.entries(providerWeights).map(([provider, weight]) => (
                    <div key={provider} className="provider-slider">
                      <span className="provider-slider-label">
                        <span>{PROVIDER_LABELS[provider] ?? provider}</span>
                        <span>{Math.round(weight * 100)}%</span>
                      </span>
                      <Slider
                        min={0}
                        max={100}
                        value={Math.round(weight * 100)}
                        disabled={uiLocked || oracleBusy}
                        onChange={(value) => updateProviderWeight(provider, Number(value) / 100)}
                      />
                    </div>
                  ))}
                </div>
                {oracleMode === "chaos" && (
                  <div className="control-deck-row">
                    <span className="pane-meta">Chaos Intensity</span>
                    <SegmentedControl
                      data={CHAOS_INTENSITY_OPTIONS}
                      value={chaosIntensity}
                      onChange={(value) => setChaosIntensity(value as "low" | "medium" | "high")}
                      disabled={uiLocked || oracleBusy}
                      size="xs"
                      fullWidth
                    />
                  </div>
                )}
                {providerStatusSummary.length > 0 && (
                  <div className="control-deck-status">
                    {providerStatusSummary.map((item) => (
                      <div key={item.key} className={`provider-status-chip ${item.status === "online" ? "is-online" : "is-offline"}`}>
                        <Group justify="space-between" gap={6}>
                          <span>{item.label}</span>
                          <Badge color={item.status === "online" ? "lyra" : "red"}>{item.weightPct}%</Badge>
                        </Group>
                        <span>{item.detail}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
            <div className="mode-row">
              <SegmentedControl
                data={ORACLE_MODE_OPTIONS}
                value={oracleMode}
                onChange={(value) => setOracleMode(value as OracleMode)}
                disabled={uiLocked}
                size="xs"
              />
              <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void revealOraclePicks()}>
                {oracleBusy ? "Working..." : "Reveal Picks"}
              </Button>
              <Button className="lyra-button lyra-button--accent" variant="filled" color="lyra" disabled={uiLocked || oracleBusy} onClick={() => void submitOraclePicks()}>
                {oracleBusy ? "Working..." : oracleMode === "chaos" ? "Queue Chaos" : "Queue Picks"}
              </Button>
            </div>
            <div className="oracle-launchers">
              <Group className="oracle-launcher-row" align="end">
                <TextInput className="pane-input" placeholder="Vibe prompt: nocturnal jazz drift" value={vibePrompt} disabled={uiLocked || oracleBusy} onChange={(event) => setVibePrompt(event.target.value)} size="xs" styles={{ root: { flex: 1 } }} />
                <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void submitStartVibe()}>Start Vibe</Button>
              </Group>
              <Group className="oracle-launcher-row" align="end">
                <TextInput className="pane-input" placeholder="Playlust mood (optional)" value={playlustMood} disabled={uiLocked || oracleBusy} onChange={(event) => setPlaylustMood(event.target.value)} size="xs" styles={{ root: { flex: 1 } }} />
                <NumberInput className="pane-input pane-input--short" min={10} max={240} value={playlustMinutes} disabled={uiLocked || oracleBusy} onChange={(value) => setPlaylustMinutes(typeof value === "number" ? value : 60)} size="xs" />
                <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void submitPlaylust()}>Start Playlust</Button>
              </Group>
            </div>
            <div className="oracle-suggestions">
              {acquisitionSummary && <div className="pane-meta">{acquisitionSummary}</div>}
              {acquisitionStatus?.error && <div className="pane-error">{acquisitionStatus.error}</div>}
              {oracleResultMessage && <div className="pane-meta">{oracleResultMessage}</div>}
              {brokerRecommendations.length === 0 && acquisitionLeads.length === 0 && <div className="pane-meta">No brokered suggestions revealed yet.</div>}
              {brokerRecommendations.map((item) => (
                <div key={item.track.trackId} className="oracle-track-row">
                  <div className="oracle-track-main">
                    <span className="list-title">{item.track.title}</span>
                    <span className="list-meta">{item.track.artist}</span>
                    <span className="oracle-track-reason">{item.primaryReason}</span>
                    <div className="oracle-signal-row">
                      {item.providerSignals.map((signal) => (
                        <Badge key={`${item.track.trackId}-${signal.label}`} className="oracle-signal-chip" color="blue" variant="light">
                          {(PROVIDER_LABELS[String(signal.provider)] ?? signal.provider)} {Math.round(signal.score * 100)}%
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="oracle-track-actions">
                    <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void keepBrokerRecommendation(item)}>Keep</Button>
                    <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void queueBrokerRecommendation(item)}>Queue</Button>
                    <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void replayBrokerRecommendation(item)}>Play</Button>
                    <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void skipBrokerRecommendation(item)}>Skip</Button>
                  </div>
                </div>
              ))}
              {acquisitionLeads.length > 0 && (
                <section className="acquisition-radar">
                  <div className="pane-head">
                    <h2>Acquisition Radar</h2>
                  </div>
                  <div className="pane-scroll">
                    {acquisitionLeads.map((lead) => (
                      <div key={`${lead.provider}-${lead.artist}-${lead.title}`} className="acquisition-row">
                        <div className="oracle-track-main">
                          <span className="list-title">{lead.title}</span>
                          <span className="list-meta">{lead.artist}</span>
                          <span className="oracle-track-reason">{lead.reason}</span>
                        </div>
                        <div className="oracle-track-actions">
                          <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void requestAcquisitionLead(lead)}>Acquire</Button>
                          <Button className="lyra-button" variant="default" disabled={uiLocked || oracleBusy} onClick={() => void dismissAcquisitionLead(lead)}>Dismiss</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </>
        )}
      </section>

      {uiLocked && (
        <div className="unified-lock-overlay" role="status" aria-live="polite">
          <div className="unified-lock-card">
            <div className="unified-lock-title">Backend Not Ready</div>
            <div className="unified-lock-message">{bootMessage}</div>
            <Button className="lyra-button lyra-button--accent" variant="filled" color="lyra" disabled={bootRetryBusy} onClick={() => void refreshBootstrap(true)}>
              {bootRetryBusy ? "Retrying..." : "Retry Connection"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
