import type { TrackListItem } from "@/types/domain";
import { useUiStore } from "@/stores/uiStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function LibraryOmensPanel({
  tracks,
  total,
  query,
  onQueryChange,
  onPlayTrack,
  onQueueTrack,
  sortKey,
  sortDir,
  onSortChange,
  onPrevPage,
  onNextPage,
  hasPrevPage,
  hasNextPage,
}: {
  tracks: TrackListItem[];
  total: number;
  query: string;
  onQueryChange: (value: string) => void;
  onPlayTrack: (track: TrackListItem) => void;
  onQueueTrack: (track: TrackListItem) => void;
  sortKey: "title" | "artist" | "album";
  sortDir: "asc" | "desc";
  onSortChange: (value: "title" | "artist" | "album") => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  hasPrevPage: boolean;
  hasNextPage: boolean;
}) {
  const openDossier = useUiStore((state) => state.openDossier);
  return (
    <LyraPanel className="library-panel">
      <div className="section-heading">
        <h2>Library</h2>
        <span>{total} indexed tracks</span>
      </div>
      <div className="library-toolbar">
        <input
          className="command-input"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Filter by artist, title, or album"
        />
        <div className="sort-strip">
          <LyraButton onClick={() => onSortChange("artist")}>Artist {sortKey === "artist" ? sortDir : ""}</LyraButton>
          <LyraButton onClick={() => onSortChange("album")}>Album {sortKey === "album" ? sortDir : ""}</LyraButton>
          <LyraButton onClick={() => onSortChange("title")}>Title {sortKey === "title" ? sortDir : ""}</LyraButton>
        </div>
      </div>
      <div className="library-header-row">
        <span>Track</span>
        <span>Context</span>
        <span>Actions</span>
      </div>
      <div className="track-rows">
        {tracks.map((track) => (
          <div key={track.trackId} className="track-row">
            <div className="track-meta">
              <strong>{track.title}</strong>
              <span>{track.artist} · {track.album ?? "Single"}</span>
            </div>
            <div className="track-reason">{track.reason}</div>
            <div className="track-actions">
              <LyraButton onClick={() => onPlayTrack(track)}>Play</LyraButton>
              <LyraButton onClick={() => onQueueTrack(track)}>Queue</LyraButton>
              <LyraButton onClick={() => openDossier(track.trackId)}>Inspect</LyraButton>
            </div>
          </div>
        ))}
        {!tracks.length && <p className="text-dim">No tracks matched this filter.</p>}
      </div>
      <div className="library-pagination">
        <LyraButton onClick={onPrevPage} disabled={!hasPrevPage}>Prev</LyraButton>
        <LyraButton onClick={onNextPage} disabled={!hasNextPage}>Next</LyraButton>
      </div>
    </LyraPanel>
  );
}
