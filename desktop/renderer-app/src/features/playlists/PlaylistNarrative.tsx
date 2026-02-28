export function PlaylistNarrative({ beats }: { beats: string[] }) {
  return (
    <section className="lyra-panel narrative-panel">
      <div className="section-heading">
        <h2>Sequence notes</h2>
        <span>Track ordering rationale</span>
      </div>
      <ol className="story-beats">
        {beats.map((beat) => (
          <li key={beat}>{beat}</li>
        ))}
      </ol>
    </section>
  );
}
