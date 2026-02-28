import { useQuery } from "@tanstack/react-query";
import { getTrackDossier } from "@/services/lyraGateway/queries";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraPill } from "@/ui/LyraPill";

export function TrackDossierDrawer() {
  const trackId = useUiStore((state) => state.dossierTrackId);
  const close = useUiStore((state) => state.closeDossier);
  const { data } = useQuery({
    queryKey: ["dossier", trackId],
    queryFn: () => getTrackDossier(trackId ?? ""),
    enabled: Boolean(trackId),
  });

  if (!trackId || !data) {
    return null;
  }

  return (
    <div className="drawer-shell" onClick={close}>
      <LyraPanel className="dossier-drawer" onClick={(event) => event.stopPropagation()}>
        <button className="drawer-close" onClick={close}>close</button>
        <h2>{data.track.title}</h2>
        <p>{data.track.artist} · {data.fileType}</p>
        <p>{data.provenanceNotes[0]}</p>
        <div className="dossier-score-chips">
          {data.track.scoreChips.map((chip) => (
            <LyraPill key={chip.key}>{chip.label} {chip.value != null ? Math.round(chip.value * 100) : "?"}</LyraPill>
          ))}
        </div>
        {data.fact && (
          <div className="dossier-fact-drop">
            <span className="insight-kicker">Lyra intel</span>
            <p>{data.fact}</p>
          </div>
        )}
        <div className="dossier-grid">
          <div>
            <h3>Structure</h3>
            <p>BPM {Math.round(data.structure?.bpm ?? 0)}</p>
            <p>Key {data.structure?.key ?? "unknown"}</p>
            {data.structure?.hasDrop && <p>Drop at {Math.round(data.structure.dropTimestamp ?? 0)}s</p>}
          </div>
          <div>
            <h3>Lineage</h3>
            {data.lineage?.length ? (
              data.lineage.map((edge) => (
                <p key={`${edge.source}-${edge.target}`}>{edge.source} → {edge.target} <span className="text-dim">({edge.type})</span></p>
              ))
            ) : (
              <p className="text-dim">No live lineage thread loaded.</p>
            )}
          </div>
          <div>
            <h3>Samples</h3>
            {data.samples?.length ? (
              data.samples.map((s, i) => (
                <p key={i}>{s.artist} — {s.title} {s.year ? `(${s.year})` : ""}</p>
              ))
            ) : (
              <p className="text-dim">No sample provenance detected.</p>
            )}
          </div>
        </div>
      </LyraPanel>
    </div>
  );
}
