import { useEffect, useRef } from "react";
import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { audioEngine } from "@/services/audio/audioEngine";
import { reportPlayback } from "@/services/audio/playbackReporter";
import { getFactDrop } from "@/services/lyraGateway/queries";
import { useAgentStore } from "@/stores/agentStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraButton } from "@/ui/LyraButton";
import { Icon } from "@/ui/Icon";

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

  return (
    <footer className="bottom-dock lyra-panel">
      <div className="dock-track">
        <div className="track-art">{current ? current.artist[0] : "L"}</div>
        <div>
          <div className="dock-title">{current?.title ?? "Nothing playing"}</div>
          <div className="dock-subtitle">{current?.artist ?? "Select a track or start a playlist"}</div>
          {player.errorMessage && <div className="dock-fact-drop">{player.errorMessage}</div>}
          {factDrop && factDropTrackId === current?.trackId && (
            <div className="dock-fact-drop">{factDrop}</div>
          )}
        </div>
      </div>
      <div className="dock-controls">
        <LyraButton
          onClick={() => {
            if (!queue.items.length) return;
            const next = Math.max(0, queue.currentIndex - 1);
            setCurrentIndex(next);
            void audioEngine.playTrack(queue.items[next]);
          }}
        >
          {"<"}
        </LyraButton>
        <LyraButton
          onClick={() => {
            if (!current) return;
            if (player.status === "playing") {
              audioEngine.pause();
            } else if (player.status === "paused") {
              void audioEngine.play();
            } else {
              void audioEngine.playTrack(current);
            }
          }}
        >
          <Icon name={player.status === "playing" ? "pause" : "play"} className="inline-icon" />
        </LyraButton>
        <LyraButton
          onClick={() => {
            if (!queue.items.length) return;
            const next = Math.min(queue.items.length - 1, queue.currentIndex + 1);
            setCurrentIndex(next);
            void audioEngine.playTrack(queue.items[next]);
          }}
        >
          {">"}
        </LyraButton>
      </div>
      <div className="dock-progress">
        <div className="progress-rail">
          <div className="progress-fill" style={{ width: `${Math.max(2, player.progress * 100)}%` }} />
        </div>
        <div className="progress-copy">
          <span>{Math.round(player.currentTimeSec)}s</span>
          <span>{Math.round(player.durationSec)}s</span>
        </div>
      </div>
    </footer>
  );
}
