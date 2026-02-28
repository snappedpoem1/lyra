import { LyraPanel } from "@/ui/LyraPanel";

export function LibraryOmensPanel() {
  return (
    <LyraPanel className="library-panel">
      <div className="section-heading">
        <h2>Library insights</h2>
        <span>All local, all scored</span>
      </div>
      <div className="story-beats">
        <li>High-scoring tracks with low play counts detected.</li>
        <li>Tracks matching your current listening pattern available.</li>
        <li>Metadata quality verified across the active library.</li>
      </div>
    </LyraPanel>
  );
}
