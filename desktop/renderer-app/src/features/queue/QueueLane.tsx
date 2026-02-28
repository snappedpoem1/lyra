import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function QueueLane() {
  const queue = useQueueStore((state) => state.queue);
  const openDossier = useUiStore((state) => state.openDossier);
  const current = queue.items[queue.currentIndex];
  const nextUp = queue.items.slice(queue.currentIndex + 1, queue.currentIndex + 4);

  return (
    <LyraPanel className="queue-lane">
      <div className="section-heading">
        <h2>Queue runway</h2>
        <span>{queue.items.length} tracks</span>
      </div>
      <div className="queue-headline">
        <div>
          <span className="insight-kicker">Current vector</span>
          <strong>{current?.title ?? "No queue in motion"}</strong>
          <p>{current?.reason ?? "Oracle and playlist actions will stack here as a deliberate listening runway."}</p>
        </div>
        <div className="queue-headline-meta">
          <span>{queue.origin}</span>
          <span>{queue.algorithm ?? "manual tension"}</span>
        </div>
      </div>
      {nextUp.length > 0 && (
        <div className="queue-preview-strip">
          {nextUp.map((track) => (
            <button key={`preview-${track.trackId}`} className="queue-preview-card" onClick={() => openDossier(track.trackId)}>
              <span>{track.artist}</span>
              <strong>{track.title}</strong>
            </button>
          ))}
        </div>
      )}
      <div className="queue-list">
        {queue.items.map((track, index) => (
          <button key={track.trackId} className={`queue-row ${index === queue.currentIndex ? "is-current" : ""}`} onClick={() => openDossier(track.trackId)}>
            <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="queue-artist">{track.artist}</span>
            <strong className="queue-title">{track.title}</strong>
            <span className="queue-reason">{track.reason}</span>
          </button>
        ))}
      </div>
    </LyraPanel>
  );
}
