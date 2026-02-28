import { useQuery } from "@tanstack/react-query";
import { ConstellationScene } from "@/features/constellation/ConstellationScene";
import { OracleModeSwitch } from "@/features/oracle/OracleModeSwitch";
import { OracleRecommendationDeck } from "@/features/oracle/OracleRecommendationDeck";
import { audioEngine } from "@/services/audio/audioEngine";
import { getConstellation, getOracleRecommendations } from "@/services/lyraGateway/queries";
import { useOracleStore } from "@/stores/oracleStore";
import { useQueueStore } from "@/stores/queueStore";

export function OracleRoute() {
  const mode = useOracleStore((state) => state.mode);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const { data: recommendations = [] } = useQuery({
    queryKey: ["oracle", mode],
    queryFn: () => getOracleRecommendations(mode),
  });
  const { data: constellation } = useQuery({ queryKey: ["constellation"], queryFn: getConstellation });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Oracle</span>
        <h1>Intelligent recommendations from your library.</h1>
        <OracleModeSwitch />
      </section>
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
      {constellation && <ConstellationScene nodes={constellation.nodes} edges={constellation.edges} onSelectNode={() => undefined} />}
    </div>
  );
}
