import { useState } from "react";
import { Badge, Group } from "@mantine/core";
import type { BrokeredRecommendation, TrackListItem, WhatNextHint, OracleMode, RecommendationNoveltyBand } from "@/types/domain";
import { ExplanationPanel } from "@/features/explanations/ExplanationPanel";
import { FeedbackActions } from "@/features/explanations/FeedbackActions";
import { FeedbackEffectBanner } from "@/features/explanations/FeedbackEffectBanner";
import { ExplanationChips } from "@/features/explanations/ExplanationChips";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function OracleRecommendationDeck({
  recommendations,
  degraded,
  degradationSummary,
  whatNext,
  mode,
  seedTrackId,
  noveltyBand,
  onPlayTrack,
  onReplaceQueue,
}: {
  recommendations: BrokeredRecommendation[];
  degraded?: boolean;
  degradationSummary?: string;
  whatNext?: WhatNextHint[];
  mode?: OracleMode;
  seedTrackId?: string;
  noveltyBand?: RecommendationNoveltyBand;
  onPlayTrack: (track: TrackListItem) => void;
  onReplaceQueue: (tracks: TrackListItem[]) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [feedbackNotes, setFeedbackNotes] = useState<Record<string, string>>({});

  const whatNextMap = new Map(
    (whatNext ?? []).map((h) => [h.track_id, h]),
  );

  return (
    <div className="oracle-deck">
      <FeedbackEffectBanner />

      {degraded && degradationSummary && (
        <LyraPanel className="oracle-degraded-banner">
          <Badge color="orange" variant="light" size="sm">Degraded</Badge>
          <span className="oracle-degraded-text">{degradationSummary}</span>
        </LyraPanel>
      )}
      {recommendations.map((item) => {
        const id = item.track.trackId;
        const isExpanded = expandedId === id;
        const hint = whatNextMap.get(id);
        const note = feedbackNotes[id];
        return (
          <LyraPanel key={id} className={`oracle-card${isExpanded ? " oracle-card--expanded" : ""}`}>
            <div className="section-heading">
              <h3>{item.track.artist} &mdash; {item.track.title}</h3>
              <Group gap={4}>
                <ExplanationChips chips={item.explanationChips} />
                {item.confidence > 0 && (
                  <Badge size="xs" variant="outline" color="dimmed">
                    {Math.round(item.confidence * 100)}% conf
                  </Badge>
                )}
              </Group>
            </div>
            <p>{item.explanation || item.primaryReason}</p>
            {note && <p className="feedback-note">{note}</p>}
            <div className="track-actions">
              <LyraButton onClick={() => onPlayTrack(item.track)}>Play</LyraButton>
              <FeedbackActions
                trackId={id}
                artist={item.track.artist}
                title={item.track.title}
                seedTrackId={seedTrackId}
                mode={mode}
                noveltyBand={noveltyBand}
                provider={item.providerSignals[0]?.provider}
                onFeedback={(_type, effect) => {
                  if (effect) setFeedbackNotes((prev) => ({ ...prev, [id]: effect }));
                }}
              />
              <LyraButton className="lyra-button--subtle" onClick={() => setExpandedId(isExpanded ? null : id)}>
                {isExpanded ? "Hide details" : "Why this?"}
              </LyraButton>
            </div>
            {isExpanded && (
              <ExplanationPanel item={item} whatNext={hint} />
            )}
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
