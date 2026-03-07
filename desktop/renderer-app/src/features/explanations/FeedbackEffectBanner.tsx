import { useQuery } from "@tanstack/react-query";
import { getFeedbackEffects } from "@/services/lyraGateway/queries";

export function FeedbackEffectBanner() {
  const { data } = useQuery({
    queryKey: ["feedbackEffects"],
    queryFn: () => getFeedbackEffects({ limit: 5, lookback: 3600 }),
    staleTime: 30_000,
    retry: false,
  });

  if (!data || data.effects.length === 0) return null;

  return (
    <div className="feedback-effect-banner">
      <span className="feedback-effect-banner-label">Your feedback shaped this</span>
      {data.direction.signal_count > 0 && (
        <span className="feedback-effect-banner-direction">
          Leaning {data.direction.direction}: {data.direction.summary}
        </span>
      )}
      <ul className="feedback-effect-list">
        {data.effects.slice(0, 3).map((fx, i) => (
          <li key={i} className="feedback-effect-item">{fx.effect}</li>
        ))}
      </ul>
    </div>
  );
}
