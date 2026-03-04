import { useQuery } from "@tanstack/react-query";
import { getDoctorReport } from "@/services/lyraGateway/queries";
import { LyraButton } from "@/ui/LyraButton";
import type { DoctorCheck } from "@/types/domain";

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
    <section className="lyra-panel backend-status-panel">
      <div className="section-heading">
        <h2>Doctor</h2>
        <div className={`connectivity-badge ${statusClass(data?.overall ?? "FAIL")}`}>
          {data?.overall ?? "CHECK"}
        </div>
      </div>

      <div className="backend-status-grid">
        <div className="inspector-block">
          <span className="insight-kicker">Checks</span>
          <p>{data?.count ?? 0} total</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Pass</span>
          <p>{Number(data?.summary?.PASS ?? 0)}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Warnings</span>
          <p>{Number(data?.summary?.WARNING ?? 0)}</p>
        </div>
        <div className="inspector-block">
          <span className="insight-kicker">Failures</span>
          <p>{Number(data?.summary?.FAIL ?? 0)}</p>
        </div>
      </div>

      {error && (
        <div className="inspector-block">
          <span className="insight-kicker">Doctor Error</span>
          <p>{error instanceof Error ? error.message : "Doctor checks failed."}</p>
        </div>
      )}

      {isPending && !data ? (
        <div className="inspector-block">
          <span className="insight-kicker">Doctor Status</span>
          <p>Running system checks...</p>
        </div>
      ) : null}

      {data?.checks?.length ? (
        <div className="doctor-check-list">
          {data.checks.map((check) => (
            <div key={check.name} className="inspector-block doctor-check-card">
              <div className="section-heading">
                <span className="insight-kicker">{check.name}</span>
                <div className={`connectivity-badge ${statusClass(check.status)}`}>{check.status}</div>
              </div>
              <p>{check.details}</p>
            </div>
          ))}
        </div>
      ) : !isPending && !error ? (
        <div className="inspector-block">
          <span className="insight-kicker">Doctor Status</span>
          <p>No diagnostics were returned by the backend.</p>
        </div>
      ) : null}

      <div className="hero-actions">
        <LyraButton onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? "Running" : "Run doctor"}
        </LyraButton>
      </div>
    </section>
  );
}
