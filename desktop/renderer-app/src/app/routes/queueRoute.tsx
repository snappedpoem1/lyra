import { Badge, Group, Text, Title } from "@mantine/core";
import { QueueLane } from "@/features/queue/QueueLane";
import { audioEngine } from "@/services/audio/audioEngine";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function QueueRoute() {
  const queue = useQueueStore((state) => state.queue);
  const clearQueue = useQueueStore((state) => state.clearQueue);
  const player = usePlayerStore();
  const currentTrack = queue.items[queue.currentIndex] ?? null;

  return (
    <div className="route-stack">
      <LyraPanel className="queue-stage-hero">
        <div className="queue-stage-copy">
          <span className="hero-kicker">Queue Deck</span>
          <Title order={1}>Current playback order with live control.</Title>
          <Text className="queue-stage-summary">
          {currentTrack
            ? `${currentTrack.artist} / ${currentTrack.title}`
            : "Load a thread, library selection, or oracle queue to start playback."}
          </Text>
        </div>
        <Group gap="xs" className="queue-stage-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {queue.items.length} items
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {queue.origin}
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {player.status}
          </Badge>
        </Group>
        <div className="queue-stage-actions">
          <LyraButton
            className="lyra-button--accent"
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
      </LyraPanel>
      <QueueLane />
    </div>
  );
}
