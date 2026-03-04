import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { usePlayerStore } from "@/stores/playerStore";
import { audioEngine } from "@/services/audio/audioEngine";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraButton } from "@/ui/LyraButton";

export function QueueLane() {
  const queue = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);
  const moveItem = useQueueStore((state) => state.moveItem);
  const removeItem = useQueueStore((state) => state.removeItem);
  const openDossier = useUiStore((state) => state.openDossier);
  const setTrack = usePlayerStore((state) => state.setTrack);
  const current = queue.items[queue.currentIndex];
  const nextUp = queue.items.slice(queue.currentIndex + 1, queue.currentIndex + 4);

  const jumpToTrack = async (index: number) => {
    const track = queue.items[index];
    if (!track) {
      return;
    }
    setCurrentIndex(index);
    setTrack(track, "Queue", track.reasons[0]?.text ?? track.reason);
    await audioEngine.playTrack(track);
  };

  return (
    <LyraPanel className="queue-lane">
      <div className="section-heading">
        <h2>Playlist Queue</h2>
        <span>{queue.items.length} tracks</span>
      </div>
      <div className="queue-headline">
        <div>
          <span className="insight-kicker">Current row</span>
          <strong>{current?.title ?? "Queue empty"}</strong>
          <p>{current?.reasons[0]?.text ?? current?.reason ?? "Play a track or load a playlist to start."}</p>
        </div>
        <div className="queue-headline-meta">
          <span>{queue.origin}</span>
          <span>{queue.algorithm ?? "manual"}</span>
        </div>
      </div>
      {nextUp.length > 0 && (
        <div className="queue-preview-strip">
          {nextUp.map((track) => (
            <button
              key={`preview-${track.trackId}`}
              className="queue-preview-card"
              onClick={() => {
                const index = queue.items.findIndex((item) => item.trackId === track.trackId);
                void jumpToTrack(index);
              }}
            >
              <span>{track.artist}</span>
              <strong>{track.title}</strong>
            </button>
          ))}
        </div>
      )}
      <div className="queue-list">
        {queue.items.map((track, index) => (
          <div key={`${track.trackId}-${index}`} className={`queue-row ${index === queue.currentIndex ? "is-current" : ""}`}>
            <button className="queue-row-main" onClick={() => void jumpToTrack(index)}>
              <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="queue-artist">{track.artist}</span>
              <strong className="queue-title">{track.title}</strong>
              <span className="queue-reason">{track.reasons[0]?.text ?? track.reason}</span>
            </button>
            <div className="queue-row-actions">
              <LyraButton onClick={() => openDossier(track.trackId)}>Info</LyraButton>
              <LyraButton onClick={() => moveItem(index, Math.max(0, index - 1))} disabled={index === 0}>Up</LyraButton>
              <LyraButton onClick={() => moveItem(index, Math.min(queue.items.length - 1, index + 1))} disabled={index === queue.items.length - 1}>Down</LyraButton>
              <LyraButton onClick={() => removeItem(index)}>Drop</LyraButton>
            </div>
          </div>
        ))}
      </div>
    </LyraPanel>
  );
}
