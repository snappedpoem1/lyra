import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getTasteProfile } from "@/services/lyraGateway/queries";
import { requestJson } from "@/services/lyraGateway/client";
import { LyraPanel } from "@/ui/LyraPanel";

const DIM_LABELS: Record<string, string> = {
  energy: "Energy",
  valence: "Valence",
  movement: "Movement",
  tension: "Tension",
  warmth: "Warmth",
  space: "Space",
  density: "Density",
  rawness: "Rawness",
  complexity: "Complexity",
  nostalgia: "Nostalgia",
};

/** Map -1..1 to a display percentage (0..100) centred at 50 */
function toBar(v: number): number {
  return Math.round(((v + 1) / 2) * 100);
}

/** Colour: green for +, blue for -, grey near 0 */
function dimColour(v: number): string {
  const abs = Math.abs(v);
  if (abs < 0.05) return "var(--text-dim)";
  return v > 0 ? "var(--accent)" : "#6ba3f5";
}

const DECADE_ORDER = ["1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"];

export function TasteProfileCard() {
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["taste-profile"],
    queryFn: getTasteProfile,
    staleTime: 5 * 60 * 1000, // 5 min
    retry: 1,
  });

  const seed = useMutation({
    mutationFn: () =>
      requestJson("/api/taste/seed", undefined, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["taste-profile"] }),
  });

  if (isLoading) {
    return (
      <LyraPanel className="taste-card taste-card--loading">
        <span className="hero-kicker">Taste Profile</span>
        <p className="text-dim" style={{ marginTop: 6 }}>Calibrating from library…</p>
      </LyraPanel>
    );
  }

  if (isError || !data) return null;

  const {
    dimensions,
    source,
    genre_affinity,
    era_distribution,
    top_artists,
    total_signals,
    library_stats,
    is_cold_start,
  } = data;

  const totalEraTracks = Object.values(era_distribution).reduce((a, b) => a + b, 0) || 1;
  const sortedDims = Object.keys(DIM_LABELS).sort(
    (a, b) => Math.abs(dimensions[b] ?? 0) - Math.abs(dimensions[a] ?? 0),
  );

  return (
    <LyraPanel className="taste-card">
      <div className="taste-card__header">
        <span className="hero-kicker">Taste Profile</span>
        {is_cold_start && (
          <span className="taste-card__cold-badge" title="Derived from library — play tracks to refine">
            library-derived
          </span>
        )}
        {!is_cold_start && total_signals > 0 && (
          <span className="taste-card__signals">{total_signals.toLocaleString()} plays</span>
        )}
      </div>

      {is_cold_start && total_signals === 0 && (
        <p className="taste-card__hint">
          No plays recorded yet. Profile is inferred from your {library_stats.scored_tracks.toLocaleString()} scored tracks.{" "}
          <button
            className="taste-card__seed-btn"
            onClick={() => seed.mutate()}
            disabled={seed.isPending}
          >
            {seed.isPending ? "Refreshing…" : "Re-seed from library"}
          </button>
        </p>
      )}

      {/* Dimension bars */}
      <div className="taste-card__dims">
        {sortedDims.map((dim) => {
          const val = dimensions[dim] ?? 0;
          const pct = toBar(val);
          const colour = dimColour(val);
          const isSrc = source[dim];
          return (
            <div key={dim} className="taste-dim-row" title={`${isSrc} · ${val > 0 ? "+" : ""}${val.toFixed(3)}`}>
              <span className="taste-dim-label">{DIM_LABELS[dim]}</span>
              <div className="taste-dim-track">
                <div className="taste-dim-centre" />
                <div
                  className="taste-dim-bar"
                  style={{
                    width: `${Math.abs(pct - 50) * 2}%`,
                    left: val >= 0 ? "50%" : `${pct}%`,
                    background: colour,
                    opacity: isSrc === "default" ? 0.3 : 1,
                  }}
                />
              </div>
              <span className="taste-dim-val" style={{ color: colour }}>
                {val > 0 ? "+" : ""}{val.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Era strip */}
      {Object.keys(era_distribution).length > 0 && (
        <div className="taste-era">
          <span className="taste-section-label">Era</span>
          <div className="taste-era__bars">
            {DECADE_ORDER.filter((d) => era_distribution[d]).map((decade) => {
              const count = era_distribution[decade] ?? 0;
              const pct = Math.round((count / totalEraTracks) * 100);
              return (
                <div key={decade} className="taste-era__col" title={`${count} tracks`}>
                  <div className="taste-era__bar" style={{ height: `${Math.max(4, pct * 1.4)}px` }} />
                  <span className="taste-era__label">{decade.replace("s", "")}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Top artists */}
      {top_artists.length > 0 && (
        <div className="taste-artists">
          <span className="taste-section-label">Most in library</span>
          <div className="taste-artists__list">
            {top_artists.slice(0, 6).map((a) => (
              <span key={a.artist} className="taste-artist-chip">
                {a.artist}
                <span className="taste-artist-count">{a.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Genres (populated once biographer runs) */}
      {genre_affinity.length > 0 && (
        <div className="taste-genres">
          <span className="taste-section-label">Genres</span>
          <div className="taste-genres__list">
            {genre_affinity.slice(0, 8).map((g) => (
              <span key={g.genre} className="lyra-pill">{g.genre}</span>
            ))}
          </div>
        </div>
      )}
    </LyraPanel>
  );
}
