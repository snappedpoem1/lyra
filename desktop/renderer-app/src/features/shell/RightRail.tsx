import { useUiStore } from "@/stores/uiStore";
import { LyraTabs } from "@/ui/LyraTabs";
import { NowPlayingAltar } from "@/features/player/NowPlayingAltar";
import { QueueLane } from "@/features/queue/QueueLane";
import { useQuery } from "@tanstack/react-query";
import { getTrackDossier } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPill } from "@/ui/LyraPill";

export function RightRail() {
  const tab = useUiStore((state) => state.rightRailTab);
  const setTab = useUiStore((state) => state.setRightRailTab);
  const dossierTrackId = useUiStore((state) => state.dossierTrackId);
  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const { data } = useQuery({
    queryKey: ["right-rail-dossier", dossierTrackId],
    queryFn: () => getTrackDossier(dossierTrackId ?? ""),
    enabled: Boolean(dossierTrackId),
  });

  return (
    <aside className="right-rail">
      <div className="lyra-panel rail-importance">
        <div className="section-heading">
          <h2>{player.track?.title ?? "Signal standby"}</h2>
          <LyraPill>{player.status}</LyraPill>
        </div>
        <p>{player.track?.artist ?? "The right rail should become the place you keep glancing back to."}</p>
        <div className="rail-importance-grid">
          <div>
            <span className="insight-kicker">Queue heat</span>
            <strong>{queue.items.length}</strong>
          </div>
          <div>
            <span className="insight-kicker">Playback source</span>
            <strong>{player.sourceLabel ?? queue.origin}</strong>
          </div>
          <div>
            <span className="insight-kicker">Current pull</span>
            <strong>{Math.round(player.frame.energy * 100)}%</strong>
          </div>
        </div>
      </div>
      <LyraTabs>
        <button className={`tab-button ${tab === "now-playing" ? "is-active" : ""}`} onClick={() => setTab("now-playing")}>Now Playing</button>
        <button className={`tab-button ${tab === "queue" ? "is-active" : ""}`} onClick={() => setTab("queue")}>Queue</button>
        <button className={`tab-button ${tab === "details" ? "is-active" : ""}`} onClick={() => setTab("details")}>Details</button>
      </LyraTabs>
      <div className="rail-stack">
        {tab === "now-playing" && <NowPlayingAltar />}
        {tab === "queue" && <QueueLane />}
        {tab === "details" && (
          <div className="lyra-panel rail-details">
            <div className="section-heading">
              <h2>{data?.track.title ?? "Select a local artifact"}</h2>
              <LyraPill>{data?.fileType ?? "dossier"}</LyraPill>
            </div>
            <p>{data?.track.artist ?? "Track details appear here without leaving the room."}</p>
            <div className="chip-row">
              {data?.track.scoreChips.slice(0, 4).map((chip) => <span key={chip.key} className="lyra-pill">{chip.label}</span>)}
            </div>
            <div className="rail-details-grid">
              <div>
                <span className="insight-kicker">Provenance</span>
                <p>{data?.provenanceNotes[0] ?? "Metadata should feel like a collector's whisper, not a form field."}</p>
              </div>
              <div>
                <span className="insight-kicker">Acquisition</span>
                <p>{data?.acquisitionNotes[0] ?? "Acquisition path is still tracing through the archive."}</p>
              </div>
              <div>
                <span className="insight-kicker">Structure</span>
                <p>BPM {Math.round(data?.structure?.bpm ?? 0)} | {data?.structure?.key ?? "unknown key"}</p>
              </div>
              <div>
                <span className="insight-kicker">Lineage</span>
                <p>{data?.lineage?.[0] ? `${data.lineage[0].source} -> ${data.lineage[0].target}` : "No live lineage thread loaded."}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
