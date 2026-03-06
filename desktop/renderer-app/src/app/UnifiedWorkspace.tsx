import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import {
  executeOracleAction,
  getAcquisitionBootstrapStatus,
  getArtistShrine,
  getLibraryTracks,
  getOracleRecommendations,
  getTrackDossier,
  huntDeepCut,
  searchSemanticTracks,
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
import type { OracleMode, TrackDossier, TrackListItem } from "@/types/domain";

const ORACLE_MODES: OracleMode[] = ["flow", "chaos", "discovery"];
const DEFAULT_LIBRARY_LIMIT = 64;

type LibraryMode = "library" | "semantic" | "discover";

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
  const [oracleMode, setOracleMode] = useState<OracleMode>("flow");
  const [oracleSuggestions, setOracleSuggestions] = useState<TrackListItem[]>([]);
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

  const submitOraclePicks = async (): Promise<void> => {
    if (uiLocked || oracleBusy) return;
    setOracleBusy(true);
    try {
      if (oracleMode === "chaos") {
        const action = await executeOracleAction("switch_chaos_intensity", { intensity: "medium", queue_now: true });
        setOracleResultMessage(`Chaos queued ${Number(action["queued_count"] ?? 0)} tracks.`);
        await refreshBootstrap(false);
        return;
      }
      const recommendations = await getOracleRecommendations(oracleMode, currentTrack?.trackId);
      const tracks = recommendations.flatMap((item) => item.previewTracks).slice(0, 12);
      setOracleSuggestions(tracks);
      await queueTrackIds(tracks.map((track) => track.trackId), "Oracle queued recommendations");
    } catch (error) {
      setOracleResultMessage(error instanceof Error ? error.message : "Oracle action failed");
    } finally {
      setOracleBusy(false);
    }
  };

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

  const dimensionRows = DIMENSIONS.map((key) => ({ key, value: dossier?.scores[key] ?? null }));

  return (
    <div className={`unified-shell ${uiLocked ? "is-locked" : ""}`}>
      <header className="unified-header">
        <div>
          <div className="unified-brand">Lyra</div>
          <div className="unified-tag">music oracle entity</div>
        </div>
        <div className="unified-boot">{bootMessage}</div>
      </header>

      <section className="unified-grid" aria-busy={uiLocked}>
        <aside className="unified-pane library-pane">
          <div className="pane-head">
            <h2>Library</h2>
            {libraryMode === "library" && (
              <input
                className="pane-input"
                placeholder="Search artist, title, album"
                value={libraryQuery}
                disabled={uiLocked}
                onChange={(event) => setLibraryQuery(event.target.value)}
              />
            )}
          </div>

          <div className="unified-tabs">
            <button className={`lyra-button ${libraryMode === "library" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => setLibraryMode("library")}>Library</button>
            <button className={`lyra-button ${libraryMode === "semantic" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => setLibraryMode("semantic")}>Semantic</button>
            <button className={`lyra-button ${libraryMode === "discover" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => setLibraryMode("discover")}>Deep Cut</button>
          </div>

          {libraryMode === "semantic" && (
            <div className="search-strip">
              <input
                className="pane-input"
                placeholder="late-night analog dub with tension"
                value={semanticQuery}
                disabled={uiLocked || searchBusy}
                onChange={(event) => setSemanticQuery(event.target.value)}
              />
              <button className="lyra-button lyra-button--accent" disabled={uiLocked || searchBusy} onClick={() => void runSemantic()}>
                {searchBusy ? "Searching..." : "Search"}
              </button>
              <button
                className="lyra-button"
                disabled={uiLocked || semanticRows.length === 0}
                onClick={() => {
                  void queueTrackIds(semanticRows.slice(0, 10).map((row) => row.trackId), "Semantic set queued");
                }}
              >
                Queue Top
              </button>
            </div>
          )}

          {libraryMode === "discover" && (
            <div className="search-strip">
              <input
                className="pane-input"
                placeholder="genre (optional): shoegaze"
                value={discoverGenre}
                disabled={uiLocked || searchBusy}
                onChange={(event) => setDiscoverGenre(event.target.value)}
              />
              <button className="lyra-button lyra-button--accent" disabled={uiLocked || searchBusy} onClick={() => void runDeepCut()}>
                {searchBusy ? "Hunting..." : "Hunt"}
              </button>
              <button
                className="lyra-button"
                disabled={uiLocked || discoverRows.length === 0}
                onClick={() => {
                  void queueTrackIds(discoverRows.slice(0, 10).map((row) => row.track.trackId), "Deep Cut set queued");
                }}
              >
                Queue Top
              </button>
            </div>
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
                <button className="lyra-button" disabled={uiLocked} onClick={() => void queueTrackIds([row.track.trackId], "Deep Cut track queued")}>Queue</button>
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
            <button className="lyra-button" disabled={uiLocked || transportBusy} onClick={() => void transportAction("previous")}>Previous</button>
            <button className="lyra-button lyra-button--accent" disabled={uiLocked || transportBusy} onClick={() => void transportAction("play-pause")}>{player.status === "playing" ? "Pause" : "Play"}</button>
            <button className="lyra-button" disabled={uiLocked || transportBusy} onClick={() => void transportAction("next")}>Next</button>
          </div>
          <div className="seek-row">
            <span>{fmtTime(player.currentTimeSec)}</span>
            <input disabled={uiLocked} type="range" min={0} max={100} value={safeProgressPct} onChange={(event) => void onSeek(event)} />
            <span>{fmtTime(safeDuration)}</span>
          </div>
          <div className="mode-row">
            <button className={`lyra-button ${player.shuffle ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => void setPlayerMode({ shuffle: !player.shuffle })}>Shuffle {player.shuffle ? "On" : "Off"}</button>
            <button className={`lyra-button ${player.repeatMode === "off" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => void setPlayerMode({ repeat_mode: "off" })}>Repeat Off</button>
            <button className={`lyra-button ${player.repeatMode === "one" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => void setPlayerMode({ repeat_mode: "one" })}>Repeat One</button>
            <button className={`lyra-button ${player.repeatMode === "all" ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => void setPlayerMode({ repeat_mode: "all" })}>Repeat All</button>
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
                  <button className="lyra-button" disabled={uiLocked} onClick={() => void moveQueueItem(index, -1)}>Up</button>
                  <button className="lyra-button" disabled={uiLocked} onClick={() => void moveQueueItem(index, 1)}>Down</button>
                  <button className="lyra-button" disabled={uiLocked} onClick={() => void playerPlay({ queue_index: index }).then((snapshot) => applyStateSnapshot(snapshot)).catch(() => {})}>Play</button>
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
                {artistIntel.genres.length > 0 && <div className="tag-row">{artistIntel.genres.slice(0, 6).map((genre) => <span key={genre} className="tag-chip">{genre}</span>)}</div>}
                {artistIntel.bio && <p className="artist-bio-lite">{artistIntel.bio}</p>}
              </div>
            )}
          </section>
        </aside>
      </section>

      <section className={`oracle-pane ${oracleOpen ? "is-open" : "is-collapsed"}`}>
        <div className="pane-head">
          <h2>Oracle</h2>
          <button className="lyra-button" disabled={uiLocked} onClick={() => setOracleOpen((open) => !open)}>{oracleOpen ? "Collapse" : "Expand"}</button>
        </div>
        {oracleOpen && (
          <>
            <div className="mode-row">
              {ORACLE_MODES.map((mode) => (
                <button key={mode} className={`lyra-button ${oracleMode === mode ? "lyra-button--accent" : ""}`} disabled={uiLocked} onClick={() => setOracleMode(mode)}>{mode}</button>
              ))}
              <button className="lyra-button lyra-button--accent" disabled={uiLocked || oracleBusy} onClick={() => void submitOraclePicks()}>{oracleBusy ? "Building..." : "Queue Oracle Picks"}</button>
            </div>
            <div className="oracle-launchers">
              <div className="oracle-launcher-row">
                <input className="pane-input" placeholder="Vibe prompt: nocturnal jazz drift" value={vibePrompt} disabled={uiLocked || oracleBusy} onChange={(event) => setVibePrompt(event.target.value)} />
                <button className="lyra-button" disabled={uiLocked || oracleBusy} onClick={() => void submitStartVibe()}>Start Vibe</button>
              </div>
              <div className="oracle-launcher-row">
                <input className="pane-input" placeholder="Playlust mood (optional)" value={playlustMood} disabled={uiLocked || oracleBusy} onChange={(event) => setPlaylustMood(event.target.value)} />
                <input className="pane-input pane-input--short" type="number" min={10} max={240} value={playlustMinutes} disabled={uiLocked || oracleBusy} onChange={(event) => setPlaylustMinutes(Number(event.target.value))} />
                <button className="lyra-button" disabled={uiLocked || oracleBusy} onClick={() => void submitPlaylust()}>Start Playlust</button>
              </div>
            </div>
            <div className="oracle-suggestions">
              {acquisitionSummary && <div className="pane-meta">{acquisitionSummary}</div>}
              {acquisitionStatus?.error && <div className="pane-error">{acquisitionStatus.error}</div>}
              {oracleResultMessage && <div className="pane-meta">{oracleResultMessage}</div>}
              {oracleSuggestions.length === 0 && <div className="pane-meta">No oracle suggestions queued yet.</div>}
              {oracleSuggestions.map((track) => (
                <div key={track.trackId} className="oracle-track-row">
                  <span className="list-title">{track.title}</span>
                  <span className="list-meta">{track.artist}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {uiLocked && (
        <div className="unified-lock-overlay" role="status" aria-live="polite">
          <div className="unified-lock-card">
            <div className="unified-lock-title">Backend Not Ready</div>
            <div className="unified-lock-message">{bootMessage}</div>
            <button className="lyra-button lyra-button--accent" disabled={bootRetryBusy} onClick={() => void refreshBootstrap(true)}>
              {bootRetryBusy ? "Retrying..." : "Retry Connection"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
