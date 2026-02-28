import { LibraryOmensPanel } from "@/features/library/LibraryOmensPanel";

export function LibraryRoute() {
  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Library Intelligence</span>
        <h1>Local files should feel precious, inspectable, and owned.</h1>
      </section>
      <LibraryOmensPanel />
    </div>
  );
}
