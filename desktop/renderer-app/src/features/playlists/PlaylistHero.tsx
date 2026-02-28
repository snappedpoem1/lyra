import type { PlaylistDetail } from "@/types/domain";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPill } from "@/ui/LyraPill";

export function PlaylistHero({
  detail,
  onPlay,
  onQueue,
  onConstellation,
}: {
  detail: PlaylistDetail;
  onPlay: () => void;
  onQueue: () => void;
  onConstellation: () => void;
}) {
  return (
    <section className="playlist-hero lyra-panel">
      <div className="playlist-hero-copy">
        <span className="hero-kicker">Playlist</span>
        <h1>{detail.summary.title}</h1>
        <p>{detail.summary.narrative}</p>
        <div className="chip-row">
          {detail.summary.emotionalSignature.map((chip) => (
            <LyraPill key={chip.key}>{chip.key}</LyraPill>
          ))}
        </div>
        <div className="hero-stat-grid">
          <div>
            <span className="insight-kicker">Tracks</span>
            <strong>{detail.summary.trackCount}</strong>
          </div>
          <div>
            <span className="insight-kicker">Freshness</span>
            <strong>{detail.summary.freshnessLabel}</strong>
          </div>
          <div>
            <span className="insight-kicker">Last touched</span>
            <strong>{detail.summary.lastTouchedLabel ?? "Tonight"}</strong>
          </div>
        </div>
      </div>
      <div className="hero-sidecar">
        <div className="hero-sidecar-copy">
          <span className="insight-kicker">About</span>
          <p>Tracks sequenced by emotional arc, not shuffled randomly. Order matters.</p>
        </div>
        <div className="hero-actions">
          <LyraButton onClick={onPlay}>Play from top</LyraButton>
          <LyraButton onClick={onQueue}>Replace queue</LyraButton>
          <LyraButton onClick={onConstellation}>Explore connections</LyraButton>
        </div>
      </div>
    </section>
  );
}
