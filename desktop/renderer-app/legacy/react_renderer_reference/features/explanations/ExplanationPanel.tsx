import { useState } from "react";
import type { BrokeredRecommendation, WhatNextHint } from "@/types/domain";
import { ExplanationChips } from "./ExplanationChips";
import { LyraButton } from "@/ui/LyraButton";

export function ExplanationPanel({
  item,
  whatNext,
}: {
  item: BrokeredRecommendation;
  whatNext?: WhatNextHint | null;
}) {
  const [showTrace, setShowTrace] = useState(false);

  return (
    <div className="explanation-panel">
      {/* Why this */}
      <div className="explanation-why">
        <span className="explanation-label">Why this</span>
        <p className="explanation-text">{item.explanation || item.primaryReason}</p>
      </div>

      {/* Explanation chips */}
      <ExplanationChips chips={item.explanationChips} />

      {/* What next hint */}
      {whatNext && (
        <div className="explanation-what-next">
          <span className="explanation-label">Up next</span>
          <span className="explanation-what-next-hint">
            {whatNext.artist} — {whatNext.title}: {whatNext.hint}
          </span>
        </div>
      )}

      {/* Expandable evidence trace */}
      {(item.evidence.length > 0 || item.providerSignals.length > 0) && (
        <>
          <LyraButton
            className="lyra-button--subtle explanation-trace-toggle"
            onClick={() => setShowTrace(!showTrace)}
          >
            {showTrace ? "Hide trace" : "Show evidence"}
          </LyraButton>
          {showTrace && (
            <div className="explanation-trace">
              {item.providerSignals.length > 0 && (
                <div className="explanation-trace-section">
                  <span className="explanation-label">Provider signals</span>
                  <ul className="explanation-trace-list">
                    {item.providerSignals.map((s) => (
                      <li key={s.provider}>
                        <strong>{s.provider}</strong> {s.score.toFixed(3)} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {item.evidence.length > 0 && (
                <div className="explanation-trace-section">
                  <span className="explanation-label">Evidence chain</span>
                  <ul className="explanation-trace-list">
                    {item.evidence.map((e, i) => (
                      <li key={i}>
                        <span className="explanation-chip explanation-chip--provider">{e.source}</span>{" "}
                        {e.text} <span className="explanation-trace-weight">(w={e.weight.toFixed(2)})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="explanation-trace-meta">
                <span>Score: {item.brokerScore.toFixed(3)}</span>
                <span>Confidence: {Math.round(item.confidence * 100)}%</span>
                <span>Novelty: {item.noveltyBandFit}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
