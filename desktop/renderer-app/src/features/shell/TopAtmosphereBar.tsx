import { useQuery } from "@tanstack/react-query";
import { getBootStatus } from "@/services/lyraGateway/queries";

export function TopAtmosphereBar() {
  const { data } = useQuery({
    queryKey: ["boot-status"],
    queryFn: getBootStatus,
  });

  return (
    <header className="top-atmosphere">
      <div className="window-controls no-drag">
        <button onClick={() => window.lyraWindow?.minimize?.()}>-</button>
        <button onClick={() => window.lyraWindow?.maximize?.()}>[]</button>
        <button onClick={() => window.lyraWindow?.close?.()}>x</button>
      </div>
      <div>
        <div className="atmosphere-title">Lyra</div>
        <div className="atmosphere-copy">{data?.ready ? "Connected" : "Connecting..."}</div>
      </div>
      <div className="atmosphere-meta">v{window.lyraWindow?.appVersion ?? "dev"}</div>
    </header>
  );
}
