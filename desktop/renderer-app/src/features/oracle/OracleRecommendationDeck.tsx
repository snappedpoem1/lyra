import type { OracleRecommendation, TrackListItem } from "@/types/domain";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function OracleRecommendationDeck({
  recommendations,
  onPlayTrack,
  onReplaceQueue,
}: {
  recommendations: OracleRecommendation[];
  onPlayTrack: (track: TrackListItem) => void;
  onReplaceQueue: (tracks: TrackListItem[]) => void;
}) {
  return (
    <div className="oracle-deck">
      {recommendations.map((item) => (
        <LyraPanel key={item.id} className="oracle-card">
          <div className="section-heading">
            <h3>{item.title}</h3>
            <span>{item.confidenceLabel}</span>
          </div>
          <p>{item.rationale}</p>
          <div className="oracle-preview">
            {item.previewTracks.map((track) => (
              <button key={track.trackId} className="queue-row" onClick={() => onPlayTrack(track)}>
                <span>{track.artist}</span>
                <strong>{track.title}</strong>
              </button>
            ))}
          </div>
          <div className="track-actions">
            <LyraButton onClick={() => item.previewTracks[0] && onPlayTrack(item.previewTracks[0])} disabled={item.previewTracks.length === 0}>Play row</LyraButton>
            <LyraButton onClick={() => onReplaceQueue(item.previewTracks)} disabled={item.previewTracks.length === 0}>Load queue</LyraButton>
          </div>
        </LyraPanel>
      ))}
    </div>
  );
}
