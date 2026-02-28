import { QueueLane } from "@/features/queue/QueueLane";

export function QueueRoute() {
  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Queue</span>
        <h1>Up next</h1>
      </section>
      <QueueLane />
    </div>
  );
}
