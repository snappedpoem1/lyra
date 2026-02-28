import { LyraPanel } from "@/ui/LyraPanel";
import { LyraPill } from "@/ui/LyraPill";
import { LyraVisualizer } from "@/features/player/LyraVisualizer";
import { usePlayerStore } from "@/stores/playerStore";

export function NowPlayingAltar() {
  const player = usePlayerStore();
  const track = player.track;
  const metrics = [
    { label: "Energy", value: player.frame.energy },
    { label: "Tension", value: player.frame.tension },
    { label: "Movement", value: player.frame.movement },
  ];

  return (
    <LyraPanel className="now-playing-altar">
      <div className="altar-header">
        <div className="section-heading">
          <h2>Now Playing</h2>
          <LyraPill>{player.status}</LyraPill>
        </div>
        <div className="altar-status-line">
          <span>{player.sourceLabel ?? "Queue not yet possessed"}</span>
          <span>{track?.provenance ?? "Local stream unresolved"}</span>
        </div>
      </div>
      <LyraVisualizer />
      <div className="altar-core">
        <div className="altar-trackline">
          <div className="altar-art">{track ? track.artist[0] : "L"}</div>
          <div>
            <div className="altar-title">{track?.title ?? "No active invocation"}</div>
            <div className="altar-subtitle">{track?.artist ?? "Queue a playlist or oracle thread."}</div>
            <div className="altar-subtitle">{track?.album ?? "The room is waiting for a better object."}</div>
          </div>
        </div>
        <div className="altar-meters">
          {metrics.map((metric) => (
            <div key={metric.label} className="altar-meter">
              <div className="meter-label">{metric.label}</div>
              <div className="meter-bar">
                <div className="meter-fill" style={{ width: `${Math.max(8, metric.value * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="altar-insight-grid">
        <div className="altar-insight-panel">
          <span className="insight-kicker">Why now</span>
          <p className="altar-copy">{player.explanation ?? track?.reason ?? "Lyra waits for a track worthy of the room."}</p>
        </div>
        <div className="altar-insight-panel">
          <span className="insight-kicker">Collector signal</span>
          <p className="altar-copy">{track?.provenance ?? "The local file story appears once a track is active."}</p>
        </div>
      </div>
      <div className="chip-row">
        {track?.scoreChips.slice(0, 6).map((chip) => (
          <LyraPill key={chip.key}>{chip.label}</LyraPill>
        ))}
      </div>
    </LyraPanel>
  );
}
