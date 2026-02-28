import { useEffect } from "react";
import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { audioEngine } from "@/services/audio/audioEngine";
import { reportPlayback } from "@/services/audio/playbackReporter";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraButton } from "@/ui/LyraButton";
import { Icon } from "@/ui/Icon";

export function BottomTransportDock() {
  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);

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
          <div className="dock-title">{current?.title ?? "Silence waiting for a better cue"}</div>
          <div className="dock-subtitle">{current?.artist ?? "Queue a ritual to wake Lyra."}</div>
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
