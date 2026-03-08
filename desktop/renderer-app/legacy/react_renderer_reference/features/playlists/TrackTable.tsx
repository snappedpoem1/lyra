import type { TrackListItem } from "@/types/domain";
import { LyraButton } from "@/ui/LyraButton";
import { useUiStore } from "@/stores/uiStore";

export function TrackTable({ tracks, onPlayTrack }: { tracks: TrackListItem[]; onPlayTrack: (track: TrackListItem) => void }) {
  const openDossier = useUiStore((state) => state.openDossier);
  return (
    <section className="lyra-panel track-table">
      <div className="section-heading">
        <h2>Tracks</h2>
        <span>{tracks.length} tracks</span>
      </div>
      <div className="track-rows">
        {tracks.map((track, index) => (
          <div key={track.trackId} className="track-row">
            <div className="track-index">{String(index + 1).padStart(2, "0")}</div>
            <div className="track-meta">
              <strong>{track.title}</strong>
              <span>{track.artist} · {track.album}</span>
            </div>
            <div className="track-reason">{track.reasons[0]?.text ?? track.reason}</div>
            <div className="track-actions">
              <LyraButton onClick={() => onPlayTrack(track)}>Play</LyraButton>
              <LyraButton onClick={() => openDossier(track.trackId)}>Inspect</LyraButton>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
