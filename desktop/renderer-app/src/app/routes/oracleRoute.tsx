import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ConstellationScene } from "@/features/constellation/ConstellationScene";
import { OracleModeSwitch } from "@/features/oracle/OracleModeSwitch";
import { OracleRecommendationDeck } from "@/features/oracle/OracleRecommendationDeck";
import { TasteProfileCard } from "@/features/oracle/TasteProfileCard";
import { audioEngine } from "@/services/audio/audioEngine";
import { getConstellation, getOracleRecommendations } from "@/services/lyraGateway/queries";
import { useOracleStore } from "@/stores/oracleStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function OracleRoute() {
  const mode = useOracleStore((state) => state.mode);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const seedTrackId = usePlayerStore((state) => state.track?.trackId);
  const { data: recommendations = [] } = useQuery({
    queryKey: ["oracle", mode, seedTrackId],
    queryFn: () => getOracleRecommendations(mode, seedTrackId),
  });
  const { data: constellation, error: constellationError } = useQuery({
    queryKey: ["constellation"],
    queryFn: () => getConstellation(),
    staleTime: 10 * 60 * 1000,
  });
  const previewTrackCount = recommendations.reduce((total, item) => total + item.previewTracks.length, 0);
  const constellationNodeCount = constellation?.nodes.length ?? 0;
  const constellationEdgeCount = constellation?.edges.length ?? 0;

  return (
    <div className="route-stack">
      <LyraPanel className="oracle-observatory-hero">
        <div className="oracle-observatory-copy">
          <span className="hero-kicker">Oracle</span>
          <Title order={1}>Auto-DJ direction with taste memory, pivots, and live graph context.</Title>
          <Text className="oracle-observatory-summary">
            Use a mode as the steering wheel, then let Lyra surface queue-ready
            moves grounded in your library and the current seed track.
          </Text>
        </div>
        <Group gap="xs" className="oracle-observatory-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
            {mode}
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {recommendations.length} live moves
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {previewTrackCount} preview tracks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {constellationNodeCount} constellation nodes
          </Badge>
        </Group>
      </LyraPanel>

      <section className="oracle-observatory-grid">
        <LyraPanel className="oracle-observatory-card oracle-observatory-card--control">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Steering</span>
              <h2>Recommendation posture</h2>
            </div>
            <span className="home-card-meta">Seed-aware</span>
          </div>
          <p className="home-card-body-copy">
            Shift between vibe, playlust, and chaos without leaving the deck.
            The recommendations refresh against the active mode and current seed track.
          </p>
          <OracleModeSwitch />
          <div className="oracle-observatory-signal-strip">
            <div className="oracle-observatory-signal-card">
              <span className="insight-kicker">Current mode</span>
              <strong>{mode}</strong>
              <p>{seedTrackId ? "Anchored to current playback context." : "Using ambient library context."}</p>
            </div>
            <div className="oracle-observatory-signal-card">
              <span className="insight-kicker">Constellation</span>
              <strong>{constellationNodeCount} nodes / {constellationEdgeCount} edges</strong>
              <p>{constellationNodeCount > 0 ? "Graph context is loaded for nearby moves." : "Graph context will appear when available."}</p>
            </div>
          </div>
        </LyraPanel>
        <TasteProfileCard />
      </section>

      <section className="oracle-observatory-section">
        <div className="section-heading">
          <h2>Queue-ready moves</h2>
          <span>{recommendations.length} recommendations</span>
        </div>
        {recommendations.length ? (
          <OracleRecommendationDeck
            recommendations={recommendations}
            onPlayTrack={(track) => void audioEngine.playTrack(track)}
            onReplaceQueue={(tracks) =>
              replaceQueue({
                queueId: `oracle-${mode}`,
                origin: mode,
                reorderable: true,
                currentIndex: 0,
                items: tracks,
              })
            }
          />
        ) : (
          <LyraPanel className="empty-state-panel">
            The Oracle is quiet right now. Change modes or start playback to give it a stronger seed.
          </LyraPanel>
        )}
      </section>

      {constellationError ? (
        <section className="lyra-panel empty-state-panel">
          <h2>Constellation unavailable</h2>
          <p>{constellationError instanceof Error ? constellationError.message : "The constellation backend did not respond."}</p>
        </section>
      ) : constellation && constellation.nodes.length > 0 ? (
        <section className="oracle-observatory-section">
          <div className="section-heading">
            <h2>Constellation map</h2>
            <span>{constellationNodeCount} nodes / {constellationEdgeCount} edges</span>
          </div>
          <ConstellationScene
            nodes={constellation.nodes}
            edges={constellation.edges}
            onSelectNode={() => undefined}
          />
        </section>
      ) : null}
    </div>
  );
}
