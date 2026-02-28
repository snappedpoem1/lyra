import { QueueLane } from "@/features/queue/QueueLane";
import { audioEngine } from "@/services/audio/audioEngine";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraButton } from "@/ui/LyraButton";

export function QueueRoute() {
  const queue = useQueueStore((state) => state.queue);
  const clearQueue = useQueueStore((state) => state.clearQueue);
  const player = usePlayerStore();
  const currentTrack = queue.items[queue.currentIndex] ?? null;

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Playlist Queue</span>
        <h1>Current playback order</h1>
        <p>
          {currentTrack
            ? `${currentTrack.artist} | ${currentTrack.title}`
            : "Load a thread, library selection, or oracle queue to start playback."}
        </p>
        <div className="hero-actions">
          <LyraButton
            onClick={() => {
              if (currentTrack) {
                void audioEngine.playTrack(currentTrack);
              }
            }}
            disabled={!currentTrack}
          >
            Play current
          </LyraButton>
          <LyraButton
            onClick={() => {
              if (player.status === "playing") {
                audioEngine.pause();
              } else if (currentTrack) {
                void audioEngine.playTrack(currentTrack);
              }
            }}
            disabled={!currentTrack}
          >
            {player.status === "playing" ? "Pause" : "Resume"}
          </LyraButton>
          <LyraButton
            onClick={() => {
              audioEngine.stop();
              clearQueue();
            }}
            disabled={!queue.items.length}
          >
            Clear queue
          </LyraButton>
        </div>
      </section>
      <QueueLane />
    </div>
  );
}
