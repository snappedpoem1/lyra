/**
 * DimensionalSearchPanel — 10-slider dimensional search interface.
 */

import { useState, useCallback } from "react";
import { z } from "zod";
import { requestJson } from "@/services/lyraGateway/client";

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

const MOOD_PRESETS: Record<string, Partial<DimensionValues>> = {
  chill: { energy: 0.25, valence: 0.60, tension: 0.20, density: 0.30, warmth: 0.70, movement: 0.30, space: 0.65, rawness: 0.25, complexity: 0.40, nostalgia: 0.55 },
  intense: { energy: 0.85, valence: 0.45, tension: 0.80, density: 0.78, warmth: 0.28, movement: 0.85, space: 0.30, rawness: 0.78, complexity: 0.60, nostalgia: 0.35 },
  dark: { energy: 0.40, valence: 0.25, tension: 0.65, density: 0.45, warmth: 0.30, movement: 0.35, space: 0.70, rawness: 0.55, complexity: 0.45, nostalgia: 0.60 },
  euphoric: { energy: 0.78, valence: 0.88, tension: 0.20, density: 0.60, warmth: 0.72, movement: 0.72, space: 0.60, rawness: 0.28, complexity: 0.65, nostalgia: 0.45 },
};

const SearchResultSchema = z.object({
  track_id: z.string(), artist: z.string(), title: z.string(),
  album: z.string().nullable().optional(), score: z.number().optional(),
  filepath: z.string().optional(), path: z.string().optional(),
  scores: z.record(z.string(), z.number()).optional(),
  relevance_rank: z.number().nullable().optional(),
});
const SearchResponseSchema = z.object({
  results: z.array(SearchResultSchema), count: z.number().optional(), query: z.string().optional(),
});
type SearchResult = z.infer<typeof SearchResultSchema>;

function defaultValues(): DimensionValues {
  return Object.fromEntries(DIMENSIONS.map((d) => [d.id, 0.5])) as DimensionValues;
}

interface DimensionalSearchPanelProps {
  onTrackSelect?: (track: SearchResult) => void;
  initialLimit?: number;
}

export function DimensionalSearchPanel({ onTrackSelect, initialLimit = 20 }: DimensionalSearchPanelProps) {
  const [values, setValues] = useState<DimensionValues>(defaultValues);
  const [activeDims, setActiveDims] = useState<Set<DimensionId>>(new Set());
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(initialLimit);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const handleSliderChange = useCallback((dim: DimensionId, value: number) => {
    setValues((prev) => ({ ...prev, [dim]: value }));
    setActiveDims((prev) => new Set(prev).add(dim));
    setActivePreset(null);
  }, []);

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
      const dimsToSend = activeDims.size > 0 ? [...activeDims] : DIMENSIONS.map((d) => d.id);
      // Convert single values to ±0.10 ranges that hybrid_search expects
      const dimensionRanges: Record<string, [number, number]> = {};
      for (const dimId of dimsToSend) {
        const v = values[dimId];
        dimensionRanges[dimId] = [Math.max(0, v - 0.10), Math.min(1, v + 0.10)];
      }
      const data = await requestJson("/api/search/hybrid", SearchResponseSchema, {
        method: "POST",
        body: JSON.stringify({
          query: _buildQueryString(values, activeDims),
          dimension_ranges: dimensionRanges,
          top_k: limit,
          sort_by: "relevance",
        }),
      }, 12000);
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [values, activeDims, limit]);

  return (
    <section className="lyra-panel dim-panel dimensional-search-panel">
      <header>
        <span className="hero-kicker">Dimensional Search</span>
        <h2 style={{ margin: "2px 0 4px", fontSize: "var(--text-xl)", color: "var(--text)" }}>
          Shape your search across 10 emotional dimensions
        </h2>
      </header>

      <div className="dim-preset-row">
        <span className="text-dim" style={{ fontSize: "0.76rem", userSelect: "none" }}>Presets:</span>
        {Object.keys(MOOD_PRESETS).map((name) => (
          <button
            key={name}
            className={`dim-preset-btn${activePreset === name ? " is-active" : ""}`}
            onClick={() => applyPreset(name)}
          >
            {name}
          </button>
        ))}
        <button className="dim-preset-btn" onClick={resetSliders} style={{ marginLeft: 4 }}>reset</button>
      </div>

      <div className="dim-sliders">
        {DIMENSIONS.map((dim) => {
          const isActive = activeDims.has(dim.id);
          const val = values[dim.id];
          return (
            <div key={dim.id} className="dim-slider-row">
              <div className="dim-slider-header">
                <span style={{ color: isActive ? "var(--accent)" : "var(--text)", fontWeight: isActive ? 600 : 400 }}>
                  {dim.label}
                </span>
                <span className="text-dim" style={{ fontSize: "var(--text-sm)" }}>{(val * 100).toFixed(0)}</span>
              </div>
              <div className="dim-slider-track-wrap">
                <span className="dim-slider-end-label">{dim.lo}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={Math.round(val * 100)}
                  onChange={(e) => handleSliderChange(dim.id, parseInt(e.target.value, 10) / 100)}
                  style={{ width: "100%", accentColor: isActive ? "var(--accent)" : "var(--text-dim)" }}
                />
                <span className="dim-slider-end-label" style={{ textAlign: "right" }}>{dim.hi}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="dim-controls-row">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label className="text-dim" style={{ fontSize: "0.76rem" }} htmlFor="dim-limit">Limit</label>
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
        <button className="dim-search-btn" onClick={handleSearch} disabled={loading}>
          {loading ? "Searching\u2026" : `Search${activeDims.size > 0 ? ` (${activeDims.size} dims)` : ""}`}
        </button>
      </div>

      {error && <p style={{ color: "var(--warning)", fontSize: "var(--text-base)", margin: "4px 0" }}>Error: {error}</p>}

      {results.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border-divider)", paddingTop: 12, marginTop: 4 }}>
          <p className="text-dim" style={{ fontSize: "var(--text-sm)", marginBottom: 8 }}>
            {results.length} result{results.length !== 1 ? "s" : ""}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {results.map((track) => (
              <div
                key={track.track_id}
                className="dim-result-card"
                onClick={() => onTrackSelect?.(track)}
                title={`${track.artist} \u2014 ${track.title}\nScore: ${track.score != null ? (track.score * 100).toFixed(1) + "%" : "—"}`}
              >
                <span className="dim-result-artist">{track.artist}</span>
                <span className="dim-result-title">{track.title}</span>
                <span className="dim-result-score">{track.score != null ? (track.score * 100).toFixed(0) + "%" : "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

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
