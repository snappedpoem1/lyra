import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { useConnectivityStore } from "@/stores/connectivityStore";
import { useSettingsStore } from "@/stores/settingsStore";

export function BackendStatusPanel() {
  const connectivity = useConnectivityStore();
  const settings = useSettingsStore();

  return (
    <section className="lyra-panel backend-status-panel">
      <div className="section-heading">
        <h2>Backend</h2>
        <ConnectivityBadge />
      </div>
      <p>{settings.apiBaseUrl}</p>
      <p>{connectivity.lastError ?? "No recent transport errors."}</p>
      <p>Auth token {settings.apiToken ? "configured" : "not configured"}</p>
    </section>
  );
}
