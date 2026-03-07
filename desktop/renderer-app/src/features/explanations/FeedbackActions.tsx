import type { OracleMode, RecommendationNoveltyBand, FeedbackActionType } from "@/types/domain";
import { submitRecommendationFeedback } from "@/services/lyraGateway/queries";
import { LyraButton } from "@/ui/LyraButton";

interface FeedbackActionsProps {
  trackId: string;
  artist: string;
  title: string;
  seedTrackId?: string;
  mode?: OracleMode;
  noveltyBand?: RecommendationNoveltyBand;
  provider?: string;
  onFeedback?: (type: FeedbackActionType, effect?: string) => void;
}

export function FeedbackActions({
  trackId,
  artist,
  title,
  seedTrackId,
  mode,
  noveltyBand,
  provider,
  onFeedback,
}: FeedbackActionsProps) {

  const send = async (type: FeedbackActionType) => {
    const result = await submitRecommendationFeedback({
      feedbackType: type,
      trackId,
      artist,
      title,
      seedTrackId,
      mode,
      noveltyBand,
      provider,
    });
    const effect = typeof result.effect_description === "string" ? result.effect_description : undefined;
    onFeedback?.(type, effect);
  };

  return (
    <div className="feedback-actions">
      <LyraButton className="feedback-action feedback-action--keep" onClick={() => send("keep")}>
        More like this
      </LyraButton>
      <LyraButton className="feedback-action feedback-action--dismiss lyra-button--subtle" onClick={() => send("dismiss")}>
        Less like this
      </LyraButton>
    </div>
  );
}
