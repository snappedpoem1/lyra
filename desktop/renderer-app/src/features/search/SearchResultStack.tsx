import type { SearchResultGroup, TrackListItem } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraButton } from "@/ui/LyraButton";
import { useUiStore } from "@/stores/uiStore";

export function SearchResultStack({
  results,
  onPlayTrack,
}: {
  results: SearchResultGroup;
  onPlayTrack: (track: TrackListItem) => void;
}) {
  const openDossier = useUiStore((state) => state.openDossier);
  return (
    <LyraPanel className="search-stack">
      <div className="section-heading">
        <h2>Results</h2>
        <span>{results.tracks.length} tracks found</span>
      </div>
      <p className="rewrite-copy">
        {results.rewrittenQuery ? `Interpreted as: ${results.rewrittenQuery}` : "Direct match."}
      </p>
      {results.tracks.map((track) => (
        <div key={track.trackId} className="track-row">
          <div className="track-meta">
            <strong>{track.title}</strong>
            <span>{track.artist} · {track.album}</span>
          </div>
          <div className="track-reason">{track.reason}</div>
          <div className="track-actions">
            <LyraButton onClick={() => onPlayTrack(track)}>Play</LyraButton>
            <LyraButton onClick={() => openDossier(track.trackId)}>Inspect</LyraButton>
          </div>
        </div>
      ))}
    </LyraPanel>
  );
}
