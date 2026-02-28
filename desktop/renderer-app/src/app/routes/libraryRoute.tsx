import { LibraryOmensPanel } from "@/features/library/LibraryOmensPanel";

export function LibraryRoute() {
  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Library</span>
        <h1>2,472 tracks indexed and scored</h1>
      </section>
      <LibraryOmensPanel />
    </div>
  );
}
