import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { getBootStatus } from "@/services/lyraGateway/queries";
import { useConnectivityStore } from "@/stores/connectivityStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

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
    <LyraPanel className="system-stage-panel">
      <div className="system-stage-header">
        <div className="system-stage-copy">
          <span className="hero-kicker">Backend</span>
          <Title order={2}>Transport, library, and model health at a glance.</Title>
          <Text className="system-stage-summary">
            Keep the desktop path honest: endpoint status, library availability,
            model wiring, and the last visible transport failure all in one place.
          </Text>
        </div>
        <Group gap="xs" className="system-stage-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {settings.apiToken ? "Token ready" : "No token"}
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {Number(db.track_count ?? 0)} tracks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
            <ConnectivityBadge />
          </Badge>
        </Group>
      </div>

      <div className="system-stage-grid">
        <div className="system-stage-card">
          <span className="insight-kicker">Endpoint</span>
          <strong>{settings.apiBaseUrl}</strong>
          <p>Current API base used by the desktop shell.</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Auth</span>
          <strong>{settings.apiToken ? "Bearer token configured" : "No token configured"}</strong>
          <p>Token-backed access for locked or delegated runtimes.</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Library</span>
          <strong>{String(library.path ?? "unknown path")}</strong>
          <p>{library.ok ? "Readable" : "Unavailable"}</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Database</span>
          <strong>{Number(db.track_count ?? 0)} tracks</strong>
          <p>{Number(db.vibe_count ?? 0)} saved threads</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">LLM</span>
          <strong>{String(llm.provider ?? llm.base_url ?? "not reported")}</strong>
          <p>{String(llm.model ?? llm.status ?? "unavailable")}</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Last Error</span>
          <strong>{connectivity.lastError ? "Recent transport issue" : "Transport stable"}</strong>
          <p>{connectivity.lastError ?? "No recent transport errors."}</p>
        </div>
      </div>

      <div className="hero-actions">
        <LyraButton onClick={() => void refetch()} disabled={isFetching}>{isFetching ? "Checking" : "Test backend"}</LyraButton>
      </div>
    </LyraPanel>
  );
}
