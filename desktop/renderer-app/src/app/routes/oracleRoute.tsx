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

export function OracleRoute() {
  const mode = useOracleStore((state) => state.mode);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const seedTrackId = usePlayerStore((state) => state.track?.trackId);
  const { data: recommendations = [] } = useQuery({
    queryKey: ["oracle", mode],
    queryFn: () => getOracleRecommendations(mode, seedTrackId),
  });
  const { data: constellation, error: constellationError } = useQuery({
    queryKey: ["constellation"],
    queryFn: () => getConstellation(),
    staleTime: 10 * 60 * 1000,
  });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Oracle</span>
        <h1>Intelligent recommendations from your library.</h1>
        <OracleModeSwitch />
      </section>
      <TasteProfileCard />
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
      {constellationError ? (
        <section className="lyra-panel empty-state-panel">
          <h2>Constellation unavailable</h2>
          <p>{constellationError instanceof Error ? constellationError.message : "The constellation backend did not respond."}</p>
        </section>
      ) : constellation && constellation.nodes.length > 0 ? (
        <ConstellationScene
          nodes={constellation.nodes}
          edges={constellation.edges}
          onSelectNode={() => undefined}
        />
      ) : null}
    </div>
  );
}
