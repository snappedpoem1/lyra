import { useEffect, useRef } from "react";
import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { audioEngine } from "@/services/audio/audioEngine";
import { reportPlayback } from "@/services/audio/playbackReporter";
import { getFactDrop } from "@/services/lyraGateway/queries";
import { useAgentStore } from "@/stores/agentStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { Icon } from "@/ui/Icon";

function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function TrackArt({ artist, size = 48 }: { artist?: string; size?: number }) {
  const letter = artist?.trim()[0]?.toUpperCase() ?? "\u266A";
  const hue = letter.charCodeAt(0) * 37 % 360;
  return (
    <div
      className="dock-art"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, hsl(${hue},42%,22%), hsl(${(hue + 40) % 360},50%,34%))`,
        borderRadius: 8,
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

export function BottomTransportDock() {
  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);
  const factDrop = useAgentStore((state) => state.lastFactDrop);
  const factDropTrackId = useAgentStore((state) => state.factDropTrackId);
  const setFactDrop = useAgentStore((state) => state.setFactDrop);
  const lastFetchedTrackId = useRef<string | null>(null);

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
        const nextIndex = queueState.queue.currentIndex + 1;
        const nextTrack = queueState.queue.items[nextIndex];
        if (nextTrack) {
          queueState.setCurrentIndex(nextIndex);
          void audioEngine.playTrack(nextTrack);
        }
      }
    });

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
      unsubscribe();
      window.cancelAnimationFrame(animationId);
    };
  }, []);

  const current = player.track ?? queue.items[queue.currentIndex] ?? null;

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!player.durationSec) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audioEngine.element.currentTime = pct * player.durationSec;
  };

  const handleVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value);
    player.setVolume(v);
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
    // If past 5 s, restart current track; otherwise go previous
    if (player.currentTimeSec > 5) {
      audioEngine.element.currentTime = 0;
      return;
    }
    const next = Math.max(0, queue.currentIndex - 1);
    setCurrentIndex(next);
    void audioEngine.playTrack(queue.items[next]);
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

  const isPlaying = player.status === "playing";
  const volumeIcon = player.muted || player.volume === 0
    ? "volume-mute"
    : player.volume < 0.45
    ? "volume-low"
    : "volume";

  const inlineFactDrop = factDrop && factDropTrackId === current?.trackId ? factDrop : null;

  return (
    <footer className="bottom-dock lyra-panel">
      {/* Left: track info */}
      <div className="dock-left">
        <TrackArt artist={current?.artist} size={44} />
        <div className="dock-meta">
          <div className="dock-title">{current?.title ?? "Nothing playing"}</div>
          <div className="dock-subtitle">
            {current?.artist ?? "Select a track or start a vibe"}
          </div>
          {(player.errorMessage || inlineFactDrop) && (
            <div className="dock-fact-drop">
              {player.errorMessage ?? inlineFactDrop}
            </div>
          )}
        </div>
      </div>

      {/* Center: controls + seek */}
      <div className="dock-center">
        <div className="dock-controls">
          <button className="transport-btn" onClick={goPrev} title="Previous">
            <Icon name="skip-back" className="transport-icon" />
          </button>
          <button className="transport-btn transport-btn--play" onClick={togglePlay} title={isPlaying ? "Pause" : "Play"}>
            <Icon name={isPlaying ? "pause" : "play"} className="transport-icon transport-icon--lg" />
          </button>
          <button className="transport-btn" onClick={goNext} title="Next">
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
        <button className="transport-btn transport-btn--sm" onClick={toggleMute} title={player.muted ? "Unmute" : "Mute"}>
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
