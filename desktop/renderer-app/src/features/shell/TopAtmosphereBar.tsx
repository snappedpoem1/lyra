import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { getBootStatus } from "@/services/lyraGateway/queries";
import { useSettingsStore } from "@/stores/settingsStore";

const PHASE_LABELS: Record<string, string> = {
  boot: "Initializing",
  docker: "Starting Docker",
  services: "Starting services",
  llm: "Starting LM Studio",
  api: "Starting API",
  ready: "Connected",
};

export function TopAtmosphereBar() {
  const [bootMessage, setBootMessage] = useState<string | null>(null);
  const [bootReady, setBootReady] = useState(false);
  const apiBaseUrl = useSettingsStore((state) => state.apiBaseUrl);

  // IPC boot status from Electron main process
  useEffect(() => {
    const cleanup = window.lyraWindow?.onBootStatus?.((status) => {
      setBootMessage(PHASE_LABELS[status.phase] ?? status.message);
      if (status.ready) setBootReady(true);
    });
    return () => cleanup?.();
  }, []);

  // Fall back to API health polling once boot IPC reports ready (or in browser dev)
  const { data } = useQuery({
    queryKey: ["boot-status"],
    queryFn: getBootStatus,
    enabled: bootReady || !window.lyraWindow?.onBootStatus,
  });

  const statusText = bootReady || data?.ready
    ? "Connected"
    : bootMessage ?? "Connecting...";

  return (
    <header className="top-atmosphere">
      <div className="window-controls no-drag">
        <button onClick={() => window.lyraWindow?.minimize?.()}>-</button>
        <button onClick={() => window.lyraWindow?.maximize?.()}>[]</button>
        <button onClick={() => window.lyraWindow?.close?.()}>x</button>
      </div>
      <div>
        <div className="atmosphere-title">LYRA DESKTOP</div>
        <div className="atmosphere-copy">Transport: {statusText}</div>
      </div>
      <div className="atmosphere-meta">
        <ConnectivityBadge /> {apiBaseUrl} v{window.lyraWindow?.appVersion ?? "dev"}
      </div>
    </header>
  );
}
