import { QueueLane } from "@/features/queue/QueueLane";

export function QueueRoute() {
  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Queue</span>
        <h1>Queue management as pleasure.</h1>
      </section>
      <QueueLane />
    </div>
  );
}
