import type { ExplanationChipData } from "@/types/domain";

const kindColors: Record<string, string> = {
  provider: "var(--lyra)",
  reason: "var(--accent)",
  dimension: "var(--text-dim)",
  confidence: "var(--text-muted)",
  novelty: "var(--accent-alt, var(--accent))",
  feedback: "#f0b060",
  mode: "var(--text-dim)",
};

export function ExplanationChips({ chips }: { chips: ExplanationChipData[] }) {
  if (!chips || chips.length === 0) return null;
  return (
    <div className="explanation-chips">
      {chips.map((chip, i) => (
        <span
          key={`${chip.kind}-${i}`}
          className={`explanation-chip explanation-chip--${chip.kind}`}
          style={{ borderColor: kindColors[chip.kind] ?? "var(--border)" }}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}
