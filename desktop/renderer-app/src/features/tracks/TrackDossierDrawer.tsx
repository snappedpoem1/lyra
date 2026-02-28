import { useQuery } from "@tanstack/react-query";
import { getTrackDossier } from "@/services/lyraGateway/queries";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";

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
        <div className="dossier-grid">
          <div>
            <h3>Structure</h3>
            <p>BPM {Math.round(data.structure?.bpm ?? 0)}</p>
            <p>Key {data.structure?.key ?? "unknown"}</p>
          </div>
          <div>
            <h3>Lineage</h3>
            {data.lineage?.map((edge) => (
              <p key={`${edge.source}-${edge.target}`}>{edge.source} → {edge.target}</p>
            ))}
          </div>
        </div>
      </LyraPanel>
    </div>
  );
}
