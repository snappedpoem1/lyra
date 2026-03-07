import { useEffect, useRef } from "react";
import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { audioEngine } from "@/services/audio/audioEngine";
import { listenHostBootStatus, listenHostTransport } from "@/services/host/tauriHost";
import { reportPlayback } from "@/services/audio/playbackReporter";
import { getFactDrop } from "@/services/lyraGateway/queries";
import { useAgentStore } from "@/stores/agentStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { usePersistentState } from "@/features/native/usePersistentState";
import { Icon } from "@/ui/Icon";

function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function TrackArt({ artist, size = 40 }: { artist?: string; size?: number }) {
  const letter = artist?.trim()[0]?.toUpperCase() ?? "\u266A";
  const hue = letter.charCodeAt(0) * 37 % 360;
  return (
    <div
      className="dock-art"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, hsl(${hue},42%,22%), hsl(${(hue + 40) % 360},50%,34%))`,
        borderRadius: 6,
        display: "grid",
        placeItems: "center",
        fontSize: size * 0.42,
        fontWeight: 600,
        color: `hsl(${hue},60%,86%)`,
        flexShrink: 0,
        letterSpacing: "-0.01em",
        userSelect: "none",
      }}
      aria-hidden="true"
    >
      {letter}
    </div>
  );
}

/** Canvas mini-waveform — reads from playerStore directly to avoid React re-render overhead. */
function MiniWaveform({ isPlaying }: { isPlaying: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef    = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const BAR_COUNT = 32;
    const ACCENT = "#8cd94a";
    const DIM    = "rgba(140,217,74,0.22)";

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const frame    = usePlayerStore.getState().frame;
      const waveform = frame.waveform;
      const playing  = usePlayerStore.getState().status === "playing";

      const step     = Math.floor(waveform.length / BAR_COUNT);
      const barW     = Math.floor(w / BAR_COUNT) - 1;

      for (let i = 0; i < BAR_COUNT; i++) {
        const val   = waveform[i * step] ?? 0;
        const barH  = Math.max(2, val * h * 0.9);
        const x     = i * (barW + 1);
        const y     = (h - barH) / 2;
        ctx.fillStyle = playing ? ACCENT : DIM;
        ctx.beginPath();
        ctx.roundRect(x, y, barW, barH, 1);
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [isPlaying]);

  return (
    <canvas
      ref={canvasRef}
      width={128}
      height={24}
      className="dock-waveform"
      aria-hidden="true"
    />
  );
}

export function BottomTransportDock() {
  const player          = usePlayerStore();
  const queue           = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);
  const factDrop        = useAgentStore((state) => state.lastFactDrop);
  const factDropTrackId = useAgentStore((state) => state.factDropTrackId);
  const setFactDrop     = useAgentStore((state) => state.setFactDrop);
  const lastFetchedTrackId = useRef<string | null>(null);
  const [persistedVolume, setPersistedVolume] = usePersistentState<number>("lyra:volume", player.volume ?? 0.82);

  useEffect(() => {
    usePlayerStore.getState().setVolume(persistedVolume);
    audioEngine.setVolume(persistedVolume);
  }, [persistedVolume]);

  useEffect(() => {
    const trackId = player.track?.trackId ?? null;
    if (trackId && trackId !== lastFetchedTrackId.current) {
      lastFetchedTrackId.current = trackId;
      void getFactDrop(trackId).then((result) => {
        setFactDrop(trackId, result.fact);
      });
    }
  }, [player.track?.trackId, setFactDrop]);

  useEffect(() => {
    audioAnalyzer.attach(audioEngine.element);
    const unsubscribe = audioEngine.subscribe(() => {
      const state = usePlayerStore.getState();
      if (state.track && state.status === "ended") {
        reportPlayback(state.track.trackId, 1, false);
        const queueState = useQueueStore.getState();
        const nextIndex  = queueState.queue.currentIndex + 1;
        const nextTrack  = queueState.queue.items[nextIndex];
        if (nextTrack) {
          queueState.setCurrentIndex(nextIndex);
          void audioEngine.playTrack(nextTrack);
        }
      }
    });

    let stopHostTransport: () => void = () => undefined;
    let stopHostBoot: () => void = () => undefined;

    const executeTransportAction = (action: string) => {
      const playerState = usePlayerStore.getState();
      const queueState = useQueueStore.getState();
      const current = playerState.track ?? queueState.queue.items[queueState.queue.currentIndex] ?? null;

      if (action === "play-pause") {
        if (!current) return;
        if (playerState.status === "playing") {
          audioEngine.pause();
          return;
        }
        if (playerState.status === "paused") {
          void audioEngine.play();
          return;
        }
        void audioEngine.playTrack(current);
        return;
      }

      if (action === "next") {
        if (!queueState.queue.items.length) return;
        const next = Math.min(queueState.queue.items.length - 1, queueState.queue.currentIndex + 1);
        queueState.setCurrentIndex(next);
        void audioEngine.playTrack(queueState.queue.items[next]);
        return;
      }

      if (action === "previous") {
        if (!queueState.queue.items.length) return;
        if (playerState.currentTimeSec > 5) {
          audioEngine.element.currentTime = 0;
          return;
        }
        const prev = Math.max(0, queueState.queue.currentIndex - 1);
        queueState.setCurrentIndex(prev);
        void audioEngine.playTrack(queueState.queue.items[prev]);
      }
    };

    void (async () => {
      stopHostTransport = await listenHostTransport((payload) => {
        executeTransportAction(payload.action);
      });

      stopHostBoot = await listenHostBootStatus((payload) => {
        if (payload.phase === "backend" && !payload.ready) {
          usePlayerStore.getState().setError(payload.message);
        }
      });
    })();

    let frame = 0;
    let animationId = 0;
    const loop = () => {
      const state = usePlayerStore.getState();
      state.setFrame(audioAnalyzer.getFrame(state.status === "playing", frame));
      frame += 1;
      animationId = window.requestAnimationFrame(loop);
    };
    animationId = window.requestAnimationFrame(loop);

    return () => {
      stopHostTransport();
      stopHostBoot();
      unsubscribe();
      window.cancelAnimationFrame(animationId);
    };
  }, []);

  const current = player.track ?? queue.items[queue.currentIndex] ?? null;

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!player.durationSec) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audioEngine.element.currentTime = pct * player.durationSec;
  };

  const handleVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value);
    player.setVolume(v);
    setPersistedVolume(v);
    audioEngine.element.volume = v;
  };

  const toggleMute = () => {
    const next = !player.muted;
    player.setMuted(next);
    audioEngine.element.muted = next;
  };

  const goNext = () => {
    if (!queue.items.length) return;
    const next = Math.min(queue.items.length - 1, queue.currentIndex + 1);
    setCurrentIndex(next);
    void audioEngine.playTrack(queue.items[next]);
  };

  const goPrev = () => {
    if (!queue.items.length) return;
    if (player.currentTimeSec > 5) {
      audioEngine.element.currentTime = 0;
      return;
    }
    const prev = Math.max(0, queue.currentIndex - 1);
    setCurrentIndex(prev);
    void audioEngine.playTrack(queue.items[prev]);
  };

  const togglePlay = () => {
    if (!current) return;
    if (player.status === "playing") {
      audioEngine.pause();
    } else if (player.status === "paused") {
      void audioEngine.play();
    } else {
      void audioEngine.playTrack(current);
    }
  };

  const isPlaying   = player.status === "playing";
  const volumeIcon  = player.muted || player.volume === 0
    ? "volume-mute"
    : player.volume < 0.45
    ? "volume-low"
    : "volume";

  const inlineFactDrop = factDrop && factDropTrackId === current?.trackId ? factDrop : null;
  const inlineExplanation = player.explanation ?? null;

  return (
    <footer className="bottom-dock">
      {/* Left: track info */}
      <div className="dock-left">
        <TrackArt artist={current?.artist} size={40} />
        <div className="dock-meta">
          <div className="dock-title">{current?.title ?? "Nothing playing"}</div>
          <div className="dock-subtitle">
            {current?.artist ?? "Select a track or start a vibe"}
          </div>
          {(player.errorMessage || inlineExplanation || inlineFactDrop) && (
            <div className="dock-fact-drop">
              {player.errorMessage ?? inlineExplanation ?? inlineFactDrop}
            </div>
          )}
        </div>
      </div>

      {/* Center: waveform + controls + seek */}
      <div className="dock-center">
        <MiniWaveform isPlaying={isPlaying} />
        <div className="dock-controls">
          <button className="transport-btn" onClick={goPrev} title="Previous  [J]">
            <Icon name="skip-back" className="transport-icon" />
          </button>
          <button
            className="transport-btn transport-btn--play"
            onClick={togglePlay}
            title={isPlaying ? "Pause  [Space]" : "Play  [Space]"}
          >
            <Icon name={isPlaying ? "pause" : "play"} className="transport-icon transport-icon--lg" />
          </button>
          <button className="transport-btn" onClick={goNext} title="Next  [K]">
            <Icon name="skip-forward" className="transport-icon" />
          </button>
        </div>
        <div className="dock-progress">
          <div
            className="progress-rail"
            role="progressbar"
            aria-label="Track progress"
            aria-valuenow={Math.round(player.progress * 100)}
            onClick={handleSeek}
          >
            <div className="progress-fill" style={{ width: `${Math.max(2, player.progress * 100)}%` }} />
            <div className="progress-thumb" style={{ left: `${Math.max(0, Math.min(100, player.progress * 100))}%` }} />
          </div>
          <div className="progress-time">
            <span>{fmtTime(player.currentTimeSec)}</span>
            <span>{fmtTime(player.durationSec)}</span>
          </div>
        </div>
      </div>

      {/* Right: volume */}
      <div className="dock-right">
        <button className="transport-btn transport-btn--sm" onClick={toggleMute} title={player.muted ? "Unmute  [M]" : "Mute  [M]"}>
          <Icon name={volumeIcon} className="transport-icon" />
        </button>
        <input
          type="range"
          className="volume-rail"
          min={0}
          max={1}
          step={0.02}
          value={player.muted ? 0 : (player.volume ?? 0.82)}
          onChange={handleVolume}
          aria-label="Volume"
        />
      </div>
    </footer>
  );
}
