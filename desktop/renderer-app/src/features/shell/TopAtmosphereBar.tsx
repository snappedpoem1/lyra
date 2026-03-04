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

  useEffect(() => {
    const cleanup = window.lyraWindow?.onBootStatus?.((status) => {
      setBootMessage(PHASE_LABELS[status.phase] ?? status.message);
      if (status.ready) setBootReady(true);
    });
    return () => cleanup?.();
  }, []);

  const { data } = useQuery({
    queryKey: ["boot-status"],
    queryFn: getBootStatus,
    enabled: bootReady || !window.lyraWindow?.onBootStatus,
  });

  const statusText = bootReady || data?.ready
    ? "Connected"
    : bootMessage ?? "Connecting\u2026";

  return (
    <header className="top-atmosphere">
      <div>
        <span className="atmosphere-copy">{statusText}</span>
      </div>
      <div className="atmosphere-meta">
        <ConnectivityBadge />
        <span>{apiBaseUrl}</span>
        <span>v{window.lyraWindow?.appVersion ?? "dev"}</span>
      </div>
      <div className="window-controls no-drag">
        <button
          className="window-control-btn window-control-btn--minimize"
          onClick={() => window.lyraWindow?.minimize?.()}
          title="Minimize"
          aria-label="Minimize"
        >&#x2015;</button>
        <button
          className="window-control-btn window-control-btn--maximize"
          onClick={() => window.lyraWindow?.maximize?.()}
          title="Maximize"
          aria-label="Maximize"
        >&#x25A1;</button>
        <button
          className="window-control-btn window-control-btn--close"
          onClick={() => window.lyraWindow?.close?.()}
          title="Close"
          aria-label="Close"
        >&#x2715;</button>
      </div>
    </header>
  );
}
