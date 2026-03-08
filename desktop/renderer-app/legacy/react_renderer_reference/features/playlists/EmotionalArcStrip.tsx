import type { PlaylistDetail } from "@/types/domain";

export function EmotionalArcStrip({ arc }: Pick<PlaylistDetail, "arc">) {
  const points = arc
    .map((point, index) => `${index * 110},${120 - point.energy * 90}`)
    .join(" ");
  return (
    <section className="lyra-panel arc-panel">
      <div className="section-heading">
        <h2>Energy curve</h2>
        <span>Across the playlist</span>
      </div>
      <svg viewBox="0 0 500 140" className="arc-svg">
        <polyline fill="none" stroke="rgba(255, 206, 150, 0.95)" strokeWidth="3" points={points} />
      </svg>
    </section>
  );
}
