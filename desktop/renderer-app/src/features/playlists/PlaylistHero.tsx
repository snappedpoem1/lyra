import type { PlaylistDetail } from "@/types/domain";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPill } from "@/ui/LyraPill";
import { PlaylistMosaic } from "@/features/playlists/PlaylistGrid";

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
        <span className="hero-kicker">Listening Thread</span>
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
            <span className="insight-kicker">Status</span>
            <strong>{detail.summary.freshnessLabel}</strong>
          </div>
          <div>
            <span className="insight-kicker">Last edited</span>
            <strong>{detail.summary.lastTouchedLabel ?? "Tonight"}</strong>
          </div>
        </div>
        <div className="hero-actions">
          <LyraButton onClick={onPlay}>Play top</LyraButton>
          <LyraButton onClick={onQueue}>Load queue</LyraButton>
          <LyraButton onClick={onConstellation}>View graph</LyraButton>
        </div>
      </div>
      <div className="hero-sidecar">
        <PlaylistMosaic
          items={detail.summary.coverMosaic?.length ? detail.summary.coverMosaic : [detail.summary.title]}
          size={120}
        />
        <div className="hero-sidecar-copy">
          <span className="insight-kicker">Thread logic</span>
          <p>Tracks are sequenced by emotional arc and library context. Order matters.</p>
        </div>
      </div>
    </section>
  );
}
