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
          <span className="hero-kicker">Home</span>
          <h1>Your library, scored and ready.</h1>
          <p>
            Pick up where you left off, explore what the oracle found, or search by sound.
          </p>
          <div className="chip-row">
            <LyraPill>2,472 tracks</LyraPill>
            <LyraPill>10-D scored</LyraPill>
            <LyraPill>local FLAC</LyraPill>
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => navigate({ to: "/playlists" })}>Playlists</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/search" })}>Search</LyraButton>
          </div>
        </section>
        <section className="lyra-panel sanctuary-status">
          <div className="section-heading">
            <h2>Quick resume</h2>
            <span>Continue listening</span>
          </div>
          <div className="sanctuary-status-grid">
            <div>
              <span className="insight-kicker">Last playlist</span>
              <strong>{leadPlaylist?.title ?? "No recent playlist"}</strong>
              <p>{leadPlaylist?.subtitle ?? "Save a vibe to see it here"}</p>
            </div>
            <div>
              <span className="insight-kicker">Underplayed</span>
              <strong>{recommendations[1]?.previewTracks[0]?.title ?? "Nothing yet"}</strong>
              <p>{recommendations[1]?.rationale ?? "Tracks scored high but rarely played."}</p>
            </div>
            <div>
              <span className="insight-kicker">Related</span>
              <strong>{secondaryPlaylist?.title ?? "No related playlists"}</strong>
              <p>{secondaryPlaylist?.narrative ?? "Build more vibes to surface connections."}</p>
            </div>
          </div>
        </section>
      </section>

      <section className="sanctuary-lanes">
        <section className="lyra-panel lane-primary">
          <div className="section-heading">
            <h2>Playlists</h2>
            <span>Saved vibes and curated sets</span>
          </div>
          <PlaylistGrid playlists={playlists} />
        </section>
        <section className="lyra-panel lane-secondary">
          <div className="section-heading">
            <h2>For you</h2>
            <span>Based on your taste profile</span>
          </div>
          <div className="sanctuary-mini-cards">
            {recommendations.map((item) => (
              <button
                key={item.id}
                className="sanctuary-mini-card"
                onClick={() =>
                  replaceQueue({
                    queueId: item.id,
                    origin: "home",
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
            origin: "home",
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
