import { useQuery } from "@tanstack/react-query";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { getBootStatus } from "@/services/lyraGateway/queries";
import { useConnectivityStore } from "@/stores/connectivityStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { LyraButton } from "@/ui/LyraButton";

export function BackendStatusPanel() {
  const connectivity = useConnectivityStore();
  const settings = useSettingsStore();
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["settings-health"],
    queryFn: getBootStatus,
  });
  const health = (connectivity.lastHealthPayload ?? data?.diagnostics ?? {}) as Record<string, unknown>;
  const db = (health.db ?? {}) as Record<string, unknown>;
  const library = (health.library ?? {}) as Record<string, unknown>;
  const llm = (health.llm ?? {}) as Record<string, unknown>;

  return (
    <section className="lyra-panel backend-status-panel">
      <div className="section-heading">
        <h2>Backend</h2>
        <ConnectivityBadge />
      </div>
      <div className="backend-status-grid">
        <div className="inspector-block">
          <span className="insight-kicker">Endpoint</span>
          <p>{settings.apiBaseUrl}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Auth</span>
          <p>{settings.apiToken ? "Bearer token configured" : "No token configured"}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Library</span>
          <p>{String(library.path ?? "unknown path")}</p>
          <p>{library.ok ? "Readable" : "Unavailable"}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Database</span>
          <p>{Number(db.track_count ?? 0)} tracks</p>
          <p>{Number(db.vibe_count ?? 0)} saved threads</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">LLM</span>
          <p>{String(llm.provider ?? llm.base_url ?? "not reported")}</p>
          <p>{String(llm.model ?? llm.status ?? "unavailable")}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Last Error</span>
          <p>{connectivity.lastError ?? "No recent transport errors."}</p>
        </div>
      </div>
      <div className="hero-actions">
        <LyraButton onClick={() => void refetch()} disabled={isFetching}>{isFetching ? "Checking" : "Test backend"}</LyraButton>
      </div>
    </section>
  );
}
