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
      // Build dimension filters — only include dims the user has touched
      const dimFilters: Partial<DimensionValues> =
        activeDims.size > 0
          ? Object.fromEntries([...activeDims].map((d) => [d, values[d]]))
          : values; // all dims if no specific selection

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
    <section className="lyra-panel dimensional-search-panel" style={panelStyle}>
      <header style={headerStyle}>
        <span className="hero-kicker">Dimensional Search</span>
        <h2 style={{ margin: "4px 0 8px", fontSize: "1.1rem", color: "var(--text)" }}>
          Shape your search across 10 emotional dimensions
        </h2>
      </header>

      {/* Preset mood buttons */}
      <div style={presetRowStyle}>
        <span style={labelStyle}>Quick presets:</span>
        {Object.keys(MOOD_PRESETS).map((name) => (
          <button
            key={name}
            onClick={() => applyPreset(name)}
            style={{
              ...presetBtnStyle,
              ...(activePreset === name ? presetActiveBtnStyle : {}),
            }}
          >
            {name}
          </button>
        ))}
        <button onClick={resetSliders} style={{ ...presetBtnStyle, marginLeft: 8, color: "var(--text-dim)" }}>
          reset
        </button>
      </div>

      {/* Sliders */}
      <div style={slidersGridStyle}>
        {DIMENSIONS.map((dim) => {
          const isActive = activeDims.has(dim.id);
          const val = values[dim.id];
          return (
            <div key={dim.id} style={sliderRowStyle}>
              <div style={dimLabelStyle}>
                <span style={{ color: isActive ? "var(--accent)" : "var(--text)", fontWeight: isActive ? 600 : 400 }}>
                  {dim.label}
                </span>
                <span style={{ color: "var(--text-dim)", fontSize: "0.72rem" }}>{(val * 100).toFixed(0)}</span>
              </div>
              <div style={sliderTrackWrapStyle}>
                <span style={sliderEndLabelStyle}>{dim.lo}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={Math.round(val * 100)}
                  onChange={(e) => handleSliderChange(dim.id, parseInt(e.target.value, 10) / 100)}
                  style={sliderInputStyle(val, isActive)}
                />
                <span style={{ ...sliderEndLabelStyle, textAlign: "right" }}>{dim.hi}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Controls */}
      <div style={controlsRowStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label style={labelStyle} htmlFor="dim-limit">Limit</label>
          <input
            id="dim-limit"
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Math.min(100, parseInt(e.target.value, 10) || 20)))}
            style={limitInputStyle}
          />
        </div>
        <button
          className="lyra-btn lyra-btn--primary"
          onClick={handleSearch}
          disabled={loading}
          style={searchBtnStyle}
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
        <div style={resultsContainerStyle}>
          <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", margin: "0 0 8px" }}>
            {results.length} result{results.length !== 1 ? "s" : ""}
          </p>
          <div style={resultsGridStyle}>
            {results.map((track) => (
              <div
                key={track.track_id}
                style={resultCardStyle}
                onClick={() => onTrackSelect?.(track)}
                title={`${track.artist} — ${track.title}\nScore: ${(track.score * 100).toFixed(1)}%`}
              >
                <div style={resultArtistStyle}>{track.artist}</div>
                <div style={resultTitleStyle}>{track.title}</div>
                <div style={resultScoreStyle}>{(track.score * 100).toFixed(0)}%</div>
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

// ─── Styles ───────────────────────────────────────────────────────────────────

const panelStyle: React.CSSProperties = {
  background: "var(--bg-elevated)",
  border: "1px solid var(--panel-border)",
  borderRadius: "var(--radius-lg)",
  padding: "20px 24px",
  display: "flex",
  flexDirection: "column",
  gap: 12,
  maxWidth: 640,
};

const headerStyle: React.CSSProperties = { marginBottom: 4 };

const presetRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  flexWrap: "wrap",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "var(--text-dim)",
  userSelect: "none",
};

const presetBtnStyle: React.CSSProperties = {
  background: "var(--bg-soft)",
  border: "1px solid var(--panel-border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-soft)",
  cursor: "pointer",
  fontSize: "0.78rem",
  padding: "3px 10px",
};

const presetActiveBtnStyle: React.CSSProperties = {
  background: "rgba(135, 214, 66, 0.18)",
  borderColor: "var(--accent)",
  color: "var(--accent)",
};

const slidersGridStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const sliderRowStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const dimLabelStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  fontSize: "0.8rem",
};

const sliderTrackWrapStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr auto 1fr",
  alignItems: "center",
  gap: 6,
};

const sliderEndLabelStyle: React.CSSProperties = {
  fontSize: "0.68rem",
  color: "var(--text-dim)",
  lineHeight: 1.2,
  maxWidth: 90,
  wordBreak: "break-word",
};

const sliderInputStyle = (val: number, isActive: boolean): React.CSSProperties => ({
  width: "100%",
  accentColor: isActive ? "var(--accent)" : "var(--text-dim)",
  cursor: "pointer",
});

const controlsRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  paddingTop: 4,
};

const limitInputStyle: React.CSSProperties = {
  width: 52,
  background: "var(--bg-soft)",
  border: "1px solid var(--panel-border)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text)",
  padding: "3px 6px",
  fontSize: "0.82rem",
};

const searchBtnStyle: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  borderRadius: "var(--radius-md)",
  color: "#111",
  cursor: "pointer",
  fontWeight: 700,
  fontSize: "0.88rem",
  padding: "7px 20px",
};

const resultsContainerStyle: React.CSSProperties = {
  borderTop: "1px solid var(--panel-border)",
  paddingTop: 12,
  marginTop: 4,
};

const resultsGridStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const resultCardStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 2fr auto",
  alignItems: "center",
  gap: 8,
  background: "var(--bg-soft)",
  border: "1px solid var(--panel-border)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 10px",
  cursor: "pointer",
};

const resultArtistStyle: React.CSSProperties = {
  color: "var(--text-dim)",
  fontSize: "0.78rem",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const resultTitleStyle: React.CSSProperties = {
  color: "var(--text)",
  fontSize: "0.85rem",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const resultScoreStyle: React.CSSProperties = {
  color: "var(--accent)",
  fontSize: "0.75rem",
  fontWeight: 600,
};
