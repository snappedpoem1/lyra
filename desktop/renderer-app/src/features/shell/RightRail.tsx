import { useUiStore } from "@/stores/uiStore";
import { LyraTabs } from "@/ui/LyraTabs";
import { NowPlayingAltar } from "@/features/player/NowPlayingAltar";
import { QueueLane } from "@/features/queue/QueueLane";
import { useQuery } from "@tanstack/react-query";
import { getAgentSuggestion, getTrackDossier } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPill } from "@/ui/LyraPill";

export function RightRail() {
  const tab = useUiStore((state) => state.rightRailTab);
  const setTab = useUiStore((state) => state.setRightRailTab);
  const dossierTrackId = useUiStore((state) => state.dossierTrackId);
  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const activeTrackId = dossierTrackId ?? player.track?.trackId ?? queue.items[queue.currentIndex]?.trackId ?? null;
  const { data } = useQuery({
    queryKey: ["right-rail-dossier", activeTrackId],
    queryFn: () => getTrackDossier(activeTrackId ?? ""),
    enabled: Boolean(activeTrackId),
  });
  const { data: suggestion } = useQuery({
    queryKey: ["agent-suggestion", player.track?.trackId],
    queryFn: () => getAgentSuggestion(player.track?.trackId),
    refetchInterval: 60_000,
  });

  return (
    <aside className="right-rail">
      <div className="lyra-panel rail-importance">
        <div className="section-heading">
          <h2>{player.track?.title ?? "Transport Ready"}</h2>
          <LyraPill>{player.status}</LyraPill>
        </div>
        <p>{player.track?.artist ?? "Playback telemetry and track details"}</p>
        <div className="rail-importance-grid">
          <div>
            <span className="insight-kicker">Queue</span>
            <strong>{queue.items.length}</strong>
          </div>
          <div>
            <span className="insight-kicker">Source</span>
            <strong>{player.sourceLabel ?? queue.origin}</strong>
          </div>
          <div>
            <span className="insight-kicker">Energy</span>
            <strong>{Math.round(player.frame.energy * 100)}%</strong>
          </div>
        </div>
        {suggestion && (
          <div className="agent-suggestion-card">
            <span className="insight-kicker">Lyra suggests</span>
            <p>{suggestion.suggestion}</p>
          </div>
        )}
      </div>
      <LyraTabs>
        <button className={`tab-button ${tab === "now-playing" ? "is-active" : ""}`} onClick={() => setTab("now-playing")}>Deck</button>
        <button className={`tab-button ${tab === "queue" ? "is-active" : ""}`} onClick={() => setTab("queue")}>Playlist</button>
        <button className={`tab-button ${tab === "details" ? "is-active" : ""}`} onClick={() => setTab("details")}>Info</button>
      </LyraTabs>
      <div className="rail-stack">
        {tab === "now-playing" && <NowPlayingAltar />}
        {tab === "queue" && <QueueLane />}
        {tab === "details" && (
          <div className="lyra-panel rail-details">
            <div className="section-heading">
              <h2>{data?.track.title ?? "No track selected"}</h2>
              <LyraPill>{data?.fileType ?? "dossier"}</LyraPill>
            </div>
            <p>{data?.track.artist ?? "Click a track to inspect it."}</p>
            <div className="chip-row">
              {data?.track.scoreChips.slice(0, 4).map((chip) => <span key={chip.key} className="lyra-pill">{chip.label}</span>)}
            </div>
            <div className="inspector-stack">
              <div className="inspector-block">
                <span className="insight-kicker">File</span>
                <p>{data?.filepath ?? "No file path loaded."}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Why</span>
                <p>{data?.track.reason ?? "No thread rationale available."}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Structure</span>
                <p>BPM {Math.round(data?.structure?.bpm ?? 0)} | {data?.structure?.key ?? "unknown key"}</p>
                <p>{data?.structure?.hasDrop ? "Drop detected in structure scan." : "No drop marker available."}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Lineage</span>
                <p>{data?.lineage?.[0] ? `${data.lineage[0].source} -> ${data.lineage[0].target}` : "No lineage data"}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Samples</span>
                <p>{data?.samples?.[0] ? `${data.samples[0].artist} - ${data.samples[0].title}` : "No sample provenance detected."}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Provenance</span>
                <p>{data?.provenanceNotes.join(" | ") || "No provenance data"}</p>
              </div>
              <div className="inspector-block">
                <span className="insight-kicker">Acquisition</span>
                <p>{data?.acquisitionNotes.join(" | ") || "No acquisition data"}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
