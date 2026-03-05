/**
 * DimensionalSearchPanel — F-012
 *
 * 10-slider dimensional search interface. Each slider controls one dimension
 * of the 10-dimensional emotional model. Triple-mode operation:
 *
 *   PRECISE — all 10 sliders active, query via /api/search (CLAP vector + score filter)
 *   MOOD    — sliders group into macro-moods (chill / intense / dark / euphoric)
 *   FREE    — freeform text query (falls back to SearchHero behaviour)
 *
 * The panel fires a live search on Submit, displaying results in a compact grid.
 *
 * Usage (drop into any page that needs dimensional search):
 *
 *   import { DimensionalSearchPanel } from "@/features/search/DimensionalSearchPanel";
 *   <DimensionalSearchPanel onTrackSelect={(track) => queue.enqueue(track)} />
 */

import { useState, useCallback } from "react";
import { z } from "zod";
import { requestJson } from "@/services/lyraGateway/client";

// ─── Dimension definitions ────────────────────────────────────────────────────

const DIMENSIONS = [
  { id: "energy",     label: "Energy",     lo: "ambient/still",      hi: "explosive/driving" },
  { id: "valence",    label: "Valence",    lo: "sad/hopeless",        hi: "ecstatic/euphoric" },
  { id: "tension",    label: "Tension",    lo: "relaxed/resolved",    hi: "horror/panic" },
  { id: "density",    label: "Density",    lo: "solo/bare",           hi: "wall-of-sound" },
  { id: "warmth",     label: "Warmth",     lo: "cold/robotic",        hi: "warm/analog/soulful" },
  { id: "movement",   label: "Movement",   lo: "frozen/drone",        hi: "driving/groove" },
  { id: "space",      label: "Space",      lo: "intimate/dry",        hi: "vast/oceanic" },
  { id: "rawness",    label: "Rawness",    lo: "polished/pristine",   hi: "distorted/lo-fi" },
  { id: "complexity", label: "Complexity", lo: "simple/repetitive",   hi: "progressive/virtuosic" },
  { id: "nostalgia",  label: "Nostalgia",  lo: "modern/futuristic",   hi: "retro/vintage" },
] as const;

type DimensionId = typeof DIMENSIONS[number]["id"];
type DimensionValues = Record<DimensionId, number>;

// Macro-mood presets — blends of dimensional values
const MOOD_PRESETS: Record<string, Partial<DimensionValues>> = {
  chill: {
    energy: 0.25, valence: 0.60, tension: 0.20, density: 0.30,
    warmth: 0.70, movement: 0.30, space: 0.65, rawness: 0.25,
    complexity: 0.40, nostalgia: 0.55,
  },
  intense: {
    energy: 0.85, valence: 0.45, tension: 0.80, density: 0.78,
    warmth: 0.28, movement: 0.85, space: 0.30, rawness: 0.78,
    complexity: 0.60, nostalgia: 0.35,
  },
  dark: {
    energy: 0.40, valence: 0.25, tension: 0.65, density: 0.45,
    warmth: 0.30, movement: 0.35, space: 0.70, rawness: 0.55,
    complexity: 0.45, nostalgia: 0.60,
  },
  euphoric: {
    energy: 0.78, valence: 0.88, tension: 0.20, density: 0.60,
    warmth: 0.72, movement: 0.72, space: 0.60, rawness: 0.28,
    complexity: 0.65, nostalgia: 0.45,
  },
};

// ─── API response schema ───────────────────────────────────────────────────────

const SearchResultSchema = z.object({
  track_id: z.string(),
  artist: z.string(),
  title: z.string(),
  album: z.string().nullable().optional(),
  score: z.number(),
  filepath: z.string().optional(),
  path: z.string().optional(),
});

const SearchResponseSchema = z.object({
  results: z.array(SearchResultSchema),
  count: z.number().optional(),
  query: z.string().optional(),
});

type SearchResult = z.infer<typeof SearchResultSchema>;

// ─── Default slider values (all centred) ──────────────────────────────────────

function defaultValues(): DimensionValues {
  return Object.fromEntries(DIMENSIONS.map((d) => [d.id, 0.5])) as DimensionValues;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface DimensionalSearchPanelProps {
  onTrackSelect?: (track: SearchResult) => void;
  initialLimit?: number;
}

export function DimensionalSearchPanel({
  onTrackSelect,
  initialLimit = 20,
}: DimensionalSearchPanelProps) {
  const [values, setValues] = useState<DimensionValues>(defaultValues);
  const [activeDims, setActiveDims] = useState<Set<DimensionId>>(new Set());
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(initialLimit);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const handleSliderChange = useCallback(
    (dim: DimensionId, value: number) => {
      setValues((prev) => ({ ...prev, [dim]: value }));
      setActiveDims((prev) => new Set(prev).add(dim));
      setActivePreset(null);
    },
    []
  );

  const applyPreset = useCallback((presetName: string) => {
    const preset = MOOD_PRESETS[presetName];
    if (!preset) return;
    setValues((prev) => ({ ...prev, ...preset }));
    setActiveDims(new Set(Object.keys(preset) as DimensionId[]));
    setActivePreset(presetName);
  }, []);

  const resetSliders = useCallback(() => {
    setValues(defaultValues());
    setActiveDims(new Set());
    setActivePreset(null);
    setResults([]);
    setError(null);
  }, []);

  const handleSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const dimFilters: Partial<DimensionValues> =
        activeDims.size > 0
          ? Object.fromEntries([...activeDims].map((d) => [d, values[d]]))
          : values;

      const data = await requestJson(
        "/api/search",
        SearchResponseSchema,
        {
          method: "POST",
          body: JSON.stringify({
            query: _buildQueryString(values, activeDims),
            dimensions: dimFilters,
            n: limit,
            use_scores: activeDims.size > 0,
          }),
        },
        12000
      );
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [values, activeDims, limit]);

  return (
    <section className="lyra-panel dimensional-search-panel dim-panel">
      <header className="dim-panel-header">
        <span className="hero-kicker">Dimensional Search</span>
        <h2 style={{ margin: "4px 0 0", fontSize: "1.05rem" }}>
          Shape your search across 10 emotional dimensions
        </h2>
      </header>

      {/* Preset mood buttons */}
      <div className="dim-preset-row">
        <span className="dim-label">Presets:</span>
        {Object.keys(MOOD_PRESETS).map((name) => (
          <button
            key={name}
            className={`dim-preset-btn${activePreset === name ? " is-active" : ""}`}
            onClick={() => applyPreset(name)}
          >
            {name}
          </button>
        ))}
        <button className="dim-preset-btn" onClick={resetSliders} style={{ marginLeft: 4, color: "var(--text-dim)" }}>
          reset
        </button>
      </div>

      {/* Sliders */}
      <div className="dim-sliders-grid">
        {DIMENSIONS.map((dim) => {
          const isActive = activeDims.has(dim.id);
          const val = values[dim.id];
          return (
            <div key={dim.id} className="dim-slider-row">
              <div className="dim-slider-label-row">
                <span className={`dim-slider-label${isActive ? " is-active" : ""}`}>
                  {dim.label}
                </span>
                <span className="dim-slider-val">{(val * 100).toFixed(0)}</span>
              </div>
              <div className="dim-slider-track-wrap">
                <span className="dim-slider-end">{dim.lo}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={Math.round(val * 100)}
                  onChange={(e) => handleSliderChange(dim.id, parseInt(e.target.value, 10) / 100)}
                  className={`dim-slider-input${isActive ? " is-active" : ""}`}
                />
                <span className="dim-slider-end dim-slider-end--right">{dim.hi}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Controls */}
      <div className="dim-controls-row">
        <div className="dim-limit-wrap">
          <label className="dim-label" htmlFor="dim-limit">Limit</label>
          <input
            id="dim-limit"
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Math.min(100, parseInt(e.target.value, 10) || 20)))}
            className="dim-limit-input"
          />
        </div>
        <button
          className="dim-search-btn"
          onClick={handleSearch}
          disabled={loading}
        >
          {loading ? "Searching…" : `Search${activeDims.size > 0 ? ` (${activeDims.size} dims)` : ""}`}
        </button>
      </div>

      {error && (
        <p style={{ color: "var(--warning)", fontSize: "0.85rem", margin: "8px 0" }}>
          Error: {error}
        </p>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="dim-results-container">
          <p className="dim-results-count">
            {results.length} result{results.length !== 1 ? "s" : ""}
          </p>
          <div className="dim-results-grid">
            {results.map((track) => (
              <div
                key={track.track_id}
                className="dim-result-card"
                onClick={() => onTrackSelect?.(track)}
                title={`${track.artist} — ${track.title}\nScore: ${(track.score * 100).toFixed(1)}%`}
              >
                <div className="dim-result-artist">{track.artist}</div>
                <div className="dim-result-title">{track.title}</div>
                <div className="dim-result-score">{(track.score * 100).toFixed(0)}%</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _buildQueryString(values: DimensionValues, activeDims: Set<DimensionId>): string {
  const dimsToUse = activeDims.size > 0 ? [...activeDims] : DIMENSIONS.map((d) => d.id);
  const parts: string[] = [];
  for (const dimId of dimsToUse) {
    const val = values[dimId];
    const dim = DIMENSIONS.find((d) => d.id === dimId);
    if (!dim) continue;
    if (val > 0.65) parts.push(dim.hi);
    else if (val < 0.35) parts.push(dim.lo);
  }
  return parts.slice(0, 5).join(", ") || "dimensional search";
}
