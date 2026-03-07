import { useState } from "react";
import { Badge, Group } from "@mantine/core";
import type { BrokeredRecommendation, TrackListItem } from "@/types/domain";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

function EvidenceTrace({ item }: { item: BrokeredRecommendation }) {
  return (
    <div className="oracle-trace">
      {item.providerSignals.length > 0 && (
        <div className="oracle-trace-section">
          <span className="oracle-trace-label">Provider signals</span>
          <table className="oracle-trace-table">
            <thead>
              <tr><th>Provider</th><th>Score</th><th>Reason</th></tr>
            </thead>
            <tbody>
              {item.providerSignals.map((s) => (
                <tr key={s.provider}>
                  <td>{s.provider}</td>
                  <td>{s.score.toFixed(3)}</td>
                  <td>{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {item.evidence.length > 0 && (
        <div className="oracle-trace-section">
          <span className="oracle-trace-label">Evidence chain</span>
          <ul className="oracle-trace-evidence">
            {item.evidence.map((e, i) => (
              <li key={i}>
                <Badge size="xs" variant="light" color="dimmed">{e.source}</Badge>{" "}
                <span className="oracle-trace-evidence-text">{e.text}</span>
                <span className="oracle-trace-evidence-weight"> (w={e.weight.toFixed(2)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="oracle-trace-meta">
        <span>Broker score: {item.brokerScore.toFixed(3)}</span>
        <span>Confidence: {(item.confidence * 100).toFixed(0)}%</span>
        <span>Novelty fit: {item.noveltyBandFit}</span>
        <span>Availability: {item.availability}</span>
      </div>
    </div>
  );
}

export function OracleRecommendationDeck({
  recommendations,
  degraded,
  degradationSummary,
  onPlayTrack,
  onReplaceQueue,
}: {
  recommendations: BrokeredRecommendation[];
  degraded?: boolean;
  degradationSummary?: string;
  onPlayTrack: (track: TrackListItem) => void;
  onReplaceQueue: (tracks: TrackListItem[]) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="oracle-deck">
      {degraded && degradationSummary && (
        <LyraPanel className="oracle-degraded-banner">
          <Badge color="orange" variant="light" size="sm">Degraded</Badge>
          <span className="oracle-degraded-text">{degradationSummary}</span>
        </LyraPanel>
      )}
      {recommendations.map((item) => {
        const id = item.track.trackId;
        const isExpanded = expandedId === id;
        return (
          <LyraPanel key={id} className={`oracle-card${isExpanded ? " oracle-card--expanded" : ""}`}>
            <div className="section-heading">
              <h3>{item.track.artist} &mdash; {item.track.title}</h3>
              <Group gap={4}>
                {item.providerSignals.map((signal) => (
                  <Badge
                    key={signal.provider}
                    size="xs"
                    variant="light"
                    color={signal.provider === "local" ? "lyra" : "midnight"}
                  >
                    {signal.provider}
                  </Badge>
                ))}
                {item.confidence > 0 && (
                  <Badge size="xs" variant="outline" color="dimmed">
                    {Math.round(item.confidence * 100)}% conf
                  </Badge>
                )}
              </Group>
            </div>
            <p>{item.explanation || item.primaryReason}</p>
            <div className="track-actions">
              <LyraButton onClick={() => onPlayTrack(item.track)}>Play</LyraButton>
              <LyraButton className="lyra-button--subtle" onClick={() => setExpandedId(isExpanded ? null : id)}>
                {isExpanded ? "Hide details" : "Why this?"}
              </LyraButton>
            </div>
            {isExpanded && <EvidenceTrace item={item} />}
          </LyraPanel>
        );
      })}
      {recommendations.length > 0 && (
        <div className="track-actions oracle-deck-actions">
          <LyraButton onClick={() => onReplaceQueue(recommendations.map((r) => r.track))}>
            Load all to queue
          </LyraButton>
        </div>
      )}
    </div>
  );
}
