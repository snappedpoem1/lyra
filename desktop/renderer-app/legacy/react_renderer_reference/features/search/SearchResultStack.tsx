import type { SearchResultGroup, TrackListItem } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraButton } from "@/ui/LyraButton";
import { useUiStore } from "@/stores/uiStore";

export function SearchResultStack({
  results,
  onPlayTrack,
  onSaveVibe,
  savePending = false,
  saveDisabled = false,
  saveLabel = "Save to Library",
}: {
  results: SearchResultGroup;
  onPlayTrack: (track: TrackListItem) => void;
  onSaveVibe?: () => void;
  savePending?: boolean;
  saveDisabled?: boolean;
  saveLabel?: string;
}) {
  const openDossier = useUiStore((state) => state.openDossier);
  return (
    <LyraPanel className="search-stack">
      <div className="section-heading">
        <h2>Results</h2>
        <div className="hero-actions">
          <span>{results.tracks.length} tracks found</span>
          {onSaveVibe && (
            <LyraButton onClick={onSaveVibe} disabled={saveDisabled || savePending}>
              {savePending ? "Saving" : saveLabel}
            </LyraButton>
          )}
        </div>
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
          <div className="track-reason">{track.reasons[0]?.text ?? track.reason}</div>
          <div className="track-actions">
            <LyraButton onClick={() => onPlayTrack(track)}>Play</LyraButton>
            <LyraButton onClick={() => openDossier(track.trackId)}>Inspect</LyraButton>
          </div>
        </div>
      ))}
    </LyraPanel>
  );
}
