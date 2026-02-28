import { QueueLane } from "@/features/queue/QueueLane";

export function QueueRoute() {
  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Playlist Queue</span>
        <h1>Current playback order</h1>
      </section>
      <QueueLane />
    </div>
  );
}
