import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ConstellationScene } from "@/features/constellation/ConstellationScene";
import { OracleRecommendationDeck } from "@/features/oracle/OracleRecommendationDeck";
import { PlaylistGrid } from "@/features/playlists/PlaylistGrid";
import { audioEngine } from "@/services/audio/audioEngine";
import { getConstellation, getOracleRecommendations, getPlaylists } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPill } from "@/ui/LyraPill";

export function HomeRoute() {
  const navigate = useNavigate();
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });
  const { data: recommendations = [] } = useQuery({ queryKey: ["oracle", "home"], queryFn: () => getOracleRecommendations("flow") });
  const { data: constellation } = useQuery({ queryKey: ["constellation"], queryFn: getConstellation });
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const leadPlaylist = playlists[0];
  const secondaryPlaylist = playlists[1];

  return (
    <div className="route-stack">
      <section className="sanctuary-grid">
        <section className="sanctuary-hero lyra-panel">
          <span className="hero-kicker">Sanctuary</span>
          <h1>Enter through mood, memory, and local possession.</h1>
          <p>
            Lyra should feel like a listening room already in progress, with a living center canvas rather than a
            poster headline.
          </p>
          <div className="chip-row">
            <LyraPill>playlist-first</LyraPill>
            <LyraPill>oracle-driven</LyraPill>
            <LyraPill>local files sacred</LyraPill>
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => navigate({ to: "/playlists" })}>Open rituals</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/search" })}>Search the room</LyraButton>
          </div>
        </section>
        <section className="lyra-panel sanctuary-status">
          <div className="section-heading">
            <h2>Current pull</h2>
            <span>Ritual continuity</span>
          </div>
          <div className="sanctuary-status-grid">
            <div>
              <span className="insight-kicker">Resume thread</span>
              <strong>{leadPlaylist?.title ?? "After Midnight Ritual"}</strong>
              <p>{leadPlaylist?.subtitle ?? "Low light, nerve glow, sacred bass weight"}</p>
            </div>
            <div>
              <span className="insight-kicker">Neglected gem</span>
              <strong>{recommendations[1]?.previewTracks[0]?.title ?? "Ash Bloom"}</strong>
              <p>{recommendations[1]?.rationale ?? "Underplayed library gravity with room to bloom."}</p>
            </div>
            <div>
              <span className="insight-kicker">Nearby pivot</span>
              <strong>{secondaryPlaylist?.title ?? "Cathedral Bass Memory"}</strong>
              <p>{secondaryPlaylist?.narrative ?? "Vast rooms, pressure, elegant ruin."}</p>
            </div>
          </div>
        </section>
      </section>

      <section className="sanctuary-lanes">
        <section className="lyra-panel lane-primary">
          <div className="section-heading">
            <h2>Ritual shelves</h2>
            <span>playlists as storytelling machines</span>
          </div>
          <PlaylistGrid playlists={playlists} />
        </section>
        <section className="lyra-panel lane-secondary">
          <div className="section-heading">
            <h2>Oracle pressure</h2>
            <span>specific, explainable, actionable</span>
          </div>
          <div className="sanctuary-mini-cards">
            {recommendations.map((item) => (
              <button
                key={item.id}
                className="sanctuary-mini-card"
                onClick={() =>
                  replaceQueue({
                    queueId: item.id,
                    origin: "sanctuary-oracle",
                    reorderable: true,
                    currentIndex: 0,
                    items: item.previewTracks,
                  })
                }
              >
                <span className="insight-kicker">{item.mode}</span>
                <strong>{item.title}</strong>
                <p>{item.rationale}</p>
              </button>
            ))}
          </div>
        </section>
      </section>

      <OracleRecommendationDeck
        recommendations={recommendations}
        onPlayTrack={(track) => void audioEngine.playTrack(track)}
        onReplaceQueue={(tracks) =>
          replaceQueue({
            queueId: "home-oracle",
            origin: "sanctuary",
            reorderable: true,
            currentIndex: 0,
            items: tracks,
          })
        }
      />

      {constellation && (
        <ConstellationScene
          nodes={constellation.nodes}
          edges={constellation.edges}
          onSelectNode={() => navigate({ to: "/oracle" })}
        />
      )}
    </div>
  );
}
