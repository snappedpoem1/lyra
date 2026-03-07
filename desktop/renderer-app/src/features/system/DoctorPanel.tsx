import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { getDoctorReport } from "@/services/lyraGateway/queries";
import { LyraButton } from "@/ui/LyraButton";
import type { DoctorCheck } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";

function statusClass(status: DoctorCheck["status"]): string {
  if (status === "PASS") {
    return "is-live";
  }
  if (status === "WARNING") {
    return "is-degraded";
  }
  return "is-fixture";
}

export function DoctorPanel() {
  const { data, isFetching, isPending, error, refetch } = useQuery({
    queryKey: ["doctor-report"],
    queryFn: getDoctorReport,
  });

  return (
    <LyraPanel className="system-stage-panel">
      <div className="system-stage-header">
        <div className="system-stage-copy">
          <span className="hero-kicker">Doctor</span>
          <Title order={2}>Runtime diagnostics with the failures surfaced before they turn into drift.</Title>
          <Text className="system-stage-summary">
            Use the doctor report to separate optional external warnings from real
            local failures in the core runtime path.
          </Text>
        </div>
        <Group gap="xs" className="system-stage-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {data?.count ?? 0} checks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {Number(data?.summary?.WARNING ?? 0)} warnings
          </Badge>
          <Badge className={`connectivity-badge ${statusClass(data?.overall ?? "FAIL")}`}>
            {data?.overall ?? "CHECK"}
          </Badge>
        </Group>
      </div>

      <div className="system-stage-grid">
        <div className="system-stage-card">
          <span className="insight-kicker">Checks</span>
          <strong>{data?.count ?? 0} total</strong>
          <p>All diagnostics returned by the backend doctor command.</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Pass</span>
          <strong>{Number(data?.summary?.PASS ?? 0)}</strong>
          <p>Healthy checks with no action required.</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Warnings</span>
          <strong>{Number(data?.summary?.WARNING ?? 0)}</strong>
          <p>Usually optional companions or degraded-but-functional states.</p>
        </div>
        <div className="system-stage-card">
          <span className="insight-kicker">Failures</span>
          <strong>{Number(data?.summary?.FAIL ?? 0)}</strong>
          <p>Checks that need correction before the runtime should be trusted.</p>
        </div>
      </div>

      {error && (
        <div className="system-stage-card">
          <span className="insight-kicker">Doctor Error</span>
          <strong>Doctor query failed</strong>
          <p>{error instanceof Error ? error.message : "Doctor checks failed."}</p>
        </div>
      )}

      {isPending && !data ? (
        <div className="system-stage-card">
          <span className="insight-kicker">Doctor Status</span>
          <strong>Running diagnostics</strong>
          <p>Running system checks...</p>
        </div>
      ) : null}

      {data?.checks?.length ? (
        <div className="doctor-check-list">
          {data.checks.map((check) => (
            <div key={check.name} className="system-stage-card doctor-check-card">
              <div className="section-heading">
                <span className="insight-kicker">{check.name}</span>
                <div className={`connectivity-badge ${statusClass(check.status)}`}>{check.status}</div>
              </div>
              <strong>{check.name}</strong>
              <p>{check.details}</p>
            </div>
          ))}
        </div>
      ) : !isPending && !error ? (
        <div className="system-stage-card">
          <span className="insight-kicker">Doctor Status</span>
          <strong>No diagnostics returned</strong>
          <p>No diagnostics were returned by the backend.</p>
        </div>
      ) : null}

      <div className="hero-actions">
        <LyraButton onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? "Running" : "Run doctor"}
        </LyraButton>
      </div>
    </LyraPanel>
  );
}
