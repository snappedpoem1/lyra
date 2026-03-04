/**
 * OracleDiscoveryPanel — The intelligence layer.
 *
 * Surfaces what makes Lyra an oracle, not just a search engine:
 * - Oracle Discover: find music you DON'T have via taste + connections
 * - Playlust: emotional arc playlists (journeys, not just lists)
 * - Deep Cuts: taste-aligned obscure gems the user hasn't heard
 * - Agent: natural language oracle queries
 */

import { useState, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { TrackListItem, OracleDiscoverySuggestion } from "@/types/domain";
import { generatePlaylust, getDeepCuts, queryAgent, getOracleDiscovery, queueOracleDiscoveries } from "@/services/lyraGateway/queries";
import { audioEngine } from "@/services/audio/audioEngine";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraButton } from "@/ui/LyraButton";

const ARC_SHAPES = [
  { id: "slow_burn", label: "Slow Burn", desc: "Gentle build to peak and resolution" },
  { id: "catharsis", label: "Catharsis", desc: "Tension → explosion → peace" },
  { id: "night_drive", label: "Night Drive", desc: "Steady cruise through ambient space" },
  { id: "heartbreak", label: "Heartbreak", desc: "Anger → grief → acceptance → hope" },
  { id: "party_wave", label: "Party Wave", desc: "Double-peak energy rollercoaster" },
  { id: "morning_light", label: "Morning Light", desc: "Gentle sunrise warmth" },
  { id: "focus_tunnel", label: "Focus Tunnel", desc: "Steady flow state immersion" },
  { id: "celebration", label: "Celebration", desc: "High-energy euphoric ride" },
];

export function OracleDiscoveryPanel() {
  const replaceQueue = useQueueStore((state) => state.replaceQueue);

  // ── Oracle Discover state ──
  const [seedArtist, setSeedArtist] = useState("");
  const [queuedArtists, setQueuedArtists] = useState<Set<string>>(new Set());
  const discoverQuery = useQuery({
    queryKey: ["oracle-discover"],
    queryFn: () => getOracleDiscovery(40),
    enabled: false,              // manual trigger only
    staleTime: 5 * 60 * 1000,   // cache for 5 min
  });
  const discoverSeedMutation = useMutation({
    mutationFn: (artist: string) => getOracleDiscovery(40, artist),
  });
  const queueMutation = useMutation({
    mutationFn: (items: OracleDiscoverySuggestion[]) =>
      queueOracleDiscoveries(items.map((s) => ({ artist: s.artist, score: s.score }))),
    onSuccess: (_, items) => {
      setQueuedArtists((prev) => {
        const next = new Set(prev);
        items.forEach((s) => next.add(s.artist));
        return next;
      });
    },
  });

  const discoverResults = discoverSeedMutation.data?.results ?? discoverQuery.data?.results ?? [];
  const discoverPending = discoverQuery.isFetching || discoverSeedMutation.isPending;

  // ── Playlust state ──
  const [playlustPrompt, setPlaylustPrompt] = useState("");
  const [selectedArc, setSelectedArc] = useState("slow_burn");
  const playlustMutation = useMutation({
    mutationFn: () => generatePlaylust(playlustPrompt, selectedArc, 20),
  });

  // ── Deep Cuts state ──
  const deepCutsMutation = useMutation({
    mutationFn: () => getDeepCuts(15),
  });

  // ── Agent state ──
  const [agentQuery, setAgentQuery] = useState("");
  const [agentResponse, setAgentResponse] = useState<string | null>(null);
  const agentMutation = useMutation({
    mutationFn: (text: string) => queryAgent(text),
    onSuccess: (data) => setAgentResponse(data.response || data.thought || "The oracle is silent."),
  });

  const playAllTracks = useCallback(
    (tracks: TrackListItem[], origin: string) => {
      if (!tracks.length) return;
      replaceQueue({
        queueId: `oracle-${origin}-${Date.now()}`,
        origin,
        reorderable: true,
        currentIndex: 0,
        items: tracks,
      });
      void audioEngine.playTrack(tracks[0]);
    },
    [replaceQueue],
  );

  return (
    <>
      {/* ── Oracle Discover: Find What You Don't Know ── */}
      <LyraPanel className="oracle-discovery-section oracle-discover-main">
        <div className="section-heading">
          <div>
            <span className="hero-kicker">The Oracle Speaks</span>
            <h2>Discover What You Don't Know</h2>
          </div>
        </div>
        <p className="text-soft" style={{ margin: "0 0 12px" }}>
          Trace connections from artists you love — collaborators, side projects, influences, scene-mates —
          and surface music you haven't acquired yet. This is what makes Lyra an oracle.
        </p>

        <form
          className="oracle-prompt-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (seedArtist.trim()) {
              discoverSeedMutation.mutate(seedArtist.trim());
            } else {
              void discoverQuery.refetch();
            }
          }}
        >
          <input
            className="hero-input"
            value={seedArtist}
            onChange={(e) => setSeedArtist(e.target.value)}
            placeholder="Seed artist (leave empty for full taste scan)..."
          />
          <LyraButton disabled={discoverPending}>
            {discoverPending ? "Consulting..." : "Discover"}
          </LyraButton>
        </form>

        {discoverResults.length > 0 && (
          <div className="oracle-result-block">
            <div className="oracle-result-header">
              <span>
                {discoverResults.length} suggestions ·{" "}
                {discoverResults.filter((s) => !s.alreadyQueued && !queuedArtists.has(s.artist)).length} fresh
              </span>
              <LyraButton
                onClick={() => {
                  const fresh = discoverResults.filter(
                    (s) => !s.alreadyQueued && !queuedArtists.has(s.artist),
                  );
                  if (fresh.length) queueMutation.mutate(fresh);
                }}
                disabled={queueMutation.isPending || discoverResults.every((s) => s.alreadyQueued || queuedArtists.has(s.artist))}
              >
                {queueMutation.isPending ? "Queueing..." : "Queue All Fresh"}
              </LyraButton>
            </div>
            <div className="oracle-discover-list">
              {discoverResults.map((suggestion, i) => {
                const isQueued = suggestion.alreadyQueued || queuedArtists.has(suggestion.artist);
                return (
                  <div key={suggestion.artist + i} className={`oracle-discover-card${isQueued ? " is-queued" : ""}`}>
                    <div className="oracle-discover-card-head">
                      <span className="oracle-discover-rank">{i + 1}</span>
                      <div className="oracle-discover-artist">
                        <strong>{suggestion.artist}</strong>
                        <span className={`oracle-conn-type oracle-conn-${suggestion.connectionType}`}>
                          {suggestion.connectionType.replace("_", " ")}
                        </span>
                      </div>
                      <div className="oracle-discover-score">
                        {suggestion.score.toFixed(2)}
                      </div>
                    </div>
                    <div className="oracle-discover-from">
                      via {suggestion.connectedFrom.join(", ")}
                    </div>
                    <div className="oracle-discover-reasons">
                      {suggestion.reasons.map((reason, ri) => (
                        <p key={ri}>{reason}</p>
                      ))}
                    </div>
                    {!isQueued && (
                      <button
                        className="oracle-discover-queue-btn"
                        onClick={() => queueMutation.mutate([suggestion])}
                        disabled={queueMutation.isPending}
                      >
                        + Queue for Acquisition
                      </button>
                    )}
                    {isQueued && <span className="oracle-discover-queued-label">Queued</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {(discoverQuery.isError || discoverSeedMutation.isError) && (
          <p className="text-dim" style={{ color: "var(--warning)", fontSize: "var(--text-sm)" }}>
            {(discoverQuery.error ?? discoverSeedMutation.error) instanceof Error
              ? (discoverQuery.error ?? discoverSeedMutation.error)!.message
              : "Discovery failed — is the backend running?"}
          </p>
        )}
      </LyraPanel>

      {/* ── Playlust: Emotional Arc Generator ── */}
      <LyraPanel className="oracle-discovery-section">
        <div className="section-heading">
          <div>
            <span className="hero-kicker">Playlust</span>
            <h2>Emotional Journeys</h2>
          </div>
        </div>
        <p className="text-soft" style={{ margin: "0 0 8px" }}>
          Shape a playlist as a journey — not random tracks, but a narrative arc with tension, release, and purpose.
        </p>

        <div className="oracle-arc-grid">
          {ARC_SHAPES.map((arc) => (
            <button
              key={arc.id}
              className={`oracle-arc-chip${selectedArc === arc.id ? " is-active" : ""}`}
              onClick={() => setSelectedArc(arc.id)}
              title={arc.desc}
            >
              {arc.label}
            </button>
          ))}
        </div>

        <form
          className="oracle-prompt-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (playlustPrompt.trim()) playlustMutation.mutate();
          }}
        >
          <input
            className="hero-input"
            value={playlustPrompt}
            onChange={(e) => setPlaylustPrompt(e.target.value)}
            placeholder="Describe the mood you want to journey through..."
          />
          <LyraButton disabled={!playlustPrompt.trim() || playlustMutation.isPending}>
            {playlustMutation.isPending ? "Building..." : "Generate Journey"}
          </LyraButton>
        </form>

        {playlustMutation.data && (
          <div className="oracle-result-block">
            <div className="oracle-result-header">
              <span>
                {playlustMutation.data.journey.length} tracks ·{" "}
                <strong>{ARC_SHAPES.find((a) => a.id === playlustMutation.data!.arc)?.label ?? playlustMutation.data.arc}</strong> arc ·{" "}
                transition smoothness: {(playlustMutation.data.transitionAvg * 100).toFixed(0)}%
              </span>
              <LyraButton onClick={() => playAllTracks(playlustMutation.data!.journey, "playlust")}>
                Play Journey
              </LyraButton>
            </div>
            <div className="oracle-track-list">
              {playlustMutation.data.journey.map((track, i) => (
                <div
                  key={track.trackId}
                  className="oracle-track-row"
                  onClick={() => void audioEngine.playTrack(track)}
                >
                  <span className="oracle-track-index">{i + 1}</span>
                  <div className="oracle-track-meta">
                    <strong>{track.title}</strong>
                    <span>{track.artist}</span>
                  </div>
                  <span className="oracle-track-label">
                    {track.reasons?.find((r) => r.type === "arc-position")?.text ?? ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </LyraPanel>

      {/* ── Deep Cuts: Taste-Aligned Hidden Gems ── */}
      <LyraPanel className="oracle-discovery-section">
        <div className="section-heading">
          <div>
            <span className="hero-kicker">Deep Cuts</span>
            <h2>What You Don't Know You Love</h2>
          </div>
          <LyraButton
            onClick={() => deepCutsMutation.mutate()}
            disabled={deepCutsMutation.isPending}
          >
            {deepCutsMutation.isPending ? "Hunting..." : "Find Deep Cuts"}
          </LyraButton>
        </div>
        <p className="text-soft" style={{ margin: "0 0 8px" }}>
          Acclaimed, obscure tracks that align with your taste profile — the Oracle reveals what you haven't explored yet.
        </p>

        {deepCutsMutation.data && deepCutsMutation.data.length > 0 && (
          <div className="oracle-result-block">
            <div className="oracle-result-header">
              <span>{deepCutsMutation.data.length} deep cuts found</span>
              <LyraButton onClick={() => playAllTracks(deepCutsMutation.data!, "deep-cuts")}>
                Play All
              </LyraButton>
            </div>
            <div className="oracle-track-list">
              {deepCutsMutation.data.map((track, i) => (
                <div
                  key={track.trackId}
                  className="oracle-track-row"
                  onClick={() => void audioEngine.playTrack(track)}
                >
                  <span className="oracle-track-index">{i + 1}</span>
                  <div className="oracle-track-meta">
                    <strong>{track.title}</strong>
                    <span>{track.artist}</span>
                  </div>
                  <span className="oracle-track-label">
                    {track.reason ?? ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {deepCutsMutation.data?.length === 0 && (
          <p className="text-dim" style={{ fontSize: "var(--text-sm)" }}>
            No deep cuts found. The Oracle needs more enrichment data — run <code>oracle enrich-all</code> to build the knowledge base.
          </p>
        )}
      </LyraPanel>

      {/* ── Oracle Agent: Natural Language Intelligence ── */}
      <LyraPanel className="oracle-discovery-section">
        <div className="section-heading">
          <div>
            <span className="hero-kicker">Ask the Oracle</span>
            <h2>Natural Language Intelligence</h2>
          </div>
        </div>
        <p className="text-soft" style={{ margin: "0 0 8px" }}>
          Ask anything about your library, taste, or music connections. The Oracle reasons across all its knowledge.
        </p>

        <form
          className="oracle-prompt-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (agentQuery.trim()) agentMutation.mutate(agentQuery.trim());
          }}
        >
          <input
            className="hero-input"
            value={agentQuery}
            onChange={(e) => setAgentQuery(e.target.value)}
            placeholder="What bridges punk and electronic? · Why does this track feel nostalgic? · Find me something I've never heard..."
          />
          <LyraButton disabled={!agentQuery.trim() || agentMutation.isPending}>
            {agentMutation.isPending ? "Thinking..." : "Ask"}
          </LyraButton>
        </form>

        {agentResponse && (
          <div className="oracle-agent-response">
            <p>{agentResponse}</p>
          </div>
        )}

        {agentMutation.isError && (
          <p className="text-dim" style={{ color: "var(--warning)", fontSize: "var(--text-sm)" }}>
            {agentMutation.error instanceof Error ? agentMutation.error.message : "Agent unavailable — is LM Studio running?"}
          </p>
        )}
      </LyraPanel>
    </>
  );
}
