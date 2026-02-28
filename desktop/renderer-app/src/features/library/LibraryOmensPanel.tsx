import { LyraPanel } from "@/ui/LyraPanel";

export function LibraryOmensPanel() {
  return (
    <LyraPanel className="library-panel">
      <div className="section-heading">
        <h2>Library omens</h2>
        <span>owned, inspectable, alive</span>
      </div>
      <div className="story-beats">
        <li>Underplayed warmth cluster found in late-night files.</li>
        <li>Several verified local cuts fit your current ritual arc.</li>
        <li>Metadata confidence is high enough to trust pivots tonight.</li>
      </div>
    </LyraPanel>
  );
}
