import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ConstellationScene } from "@/features/constellation/ConstellationScene";
import { OracleRecommendationDeck } from "@/features/oracle/OracleRecommendationDeck";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { audioEngine } from "@/services/audio/audioEngine";
import { getConstellation, getLibraryTracks, getOracleRecommendations, getPlaylistDetail, getPlaylists } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPill } from "@/ui/LyraPill";

export function HomeRoute() {
  const navigate = useNavigate();
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });
  const { data: recommendations = [] } = useQuery({ queryKey: ["oracle", "home"], queryFn: () => getOracleRecommendations("flow") });
  const { data: library } = useQuery({ queryKey: ["home-library"], queryFn: () => getLibraryTracks(10, 0, "") });
  const { data: constellation } = useQuery({ queryKey: ["constellation"], queryFn: getConstellation });
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const openDossier = useUiStore((state) => state.openDossier);
  const leadPlaylist = playlists[0];
  const secondaryPlaylist = playlists[1];
  const libraryTracks = library?.tracks ?? [];
  const playLead = async () => {
    if (!leadPlaylist) return;
    const detail = await getPlaylistDetail(leadPlaylist.id);
    replaceQueue({
      queueId: detail.summary.id,
      origin: detail.summary.title,
      reorderable: true,
      currentIndex: 0,
      items: detail.tracks,
    });
    if (detail.tracks[0]) {
      void audioEngine.playTrack(detail.tracks[0]);
    }
  };

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro player-heading">
        <div className="section-heading">
          <div>
            <span className="hero-kicker">Player Workspace</span>
            <h1>Thread, library, queue, dossier.</h1>
          </div>
          <div className="chip-row">
            <LyraPill><ConnectivityBadge /></LyraPill>
            <LyraPill>{library?.total ?? 0} library tracks</LyraPill>
            <LyraPill>{playlists.length} saved threads</LyraPill>
          </div>
        </div>
      </section>

      <section className="player-workspace">
        <section className="lyra-panel workspace-column">
          <div className="section-heading">
            <h2>Saved Threads</h2>
            <span>Lead objects</span>
          </div>
          <div className="compact-list">
            {playlists.slice(0, 6).map((playlist) => (
              <button
                key={playlist.id}
                className="thread-row"
                onClick={() => navigate({ to: "/playlists/$playlistId", params: { playlistId: playlist.id } })}
              >
                <div>
                  <strong>{playlist.title}</strong>
                  <p>{playlist.subtitle}</p>
                </div>
                <span>{playlist.trackCount}</span>
              </button>
            ))}
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => void playLead()}>Play lead</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/playlists" })}>Open threads</LyraButton>
          </div>
        </section>

        <section className="lyra-panel workspace-column">
          <div className="section-heading">
            <h2>Library Jump</h2>
            <span>Immediate access</span>
          </div>
          <div className="compact-list">
            {libraryTracks.map((track) => (
              <button
                key={track.trackId}
                className="thread-row"
                onClick={() => void audioEngine.playTrack(track)}
              >
                <div>
                  <strong>{track.title}</strong>
                  <p>{track.artist} · {track.album ?? "Single"}</p>
                </div>
                <span>{track.durationSec ? `${Math.round(track.durationSec)}s` : "--"}</span>
              </button>
            ))}
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => navigate({ to: "/library" })}>Open library</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/search" })}>Search library</LyraButton>
          </div>
        </section>

        <section className="lyra-panel workspace-column">
          <div className="section-heading">
            <h2>Auto-DJ Moves</h2>
            <span>Current pivots</span>
          </div>
          <div className="compact-list">
            {recommendations.map((item) => (
              <button
                key={item.id}
                className="thread-row"
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
                <div>
                  <span className="insight-kicker">{item.mode}</span>
                  <strong>{item.title}</strong>
                  <p>{item.rationale}</p>
                </div>
                <span>{item.previewTracks.length}</span>
              </button>
            ))}
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => navigate({ to: "/oracle" })}>Open Auto-DJ</LyraButton>
            <LyraButton onClick={() => secondaryPlaylist && navigate({ to: "/playlists/$playlistId", params: { playlistId: secondaryPlaylist.id } })}>Adjacent thread</LyraButton>
          </div>
        </section>
      </section>

      <section className="lyra-panel layers-panel">
        <div className="section-heading">
          <h2>Lyra Layers</h2>
          <span>Visible, not hidden</span>
        </div>
        <div className="layers-grid">
          <button className="layer-card" onClick={() => navigate({ to: "/library" })}>
            <span className="insight-kicker">Layer 1</span>
            <strong>Library</strong>
            <p>Real files, indexed metadata, streamable paths.</p>
          </button>
          <button className="layer-card" onClick={() => leadPlaylist && navigate({ to: "/playlists/$playlistId", params: { playlistId: leadPlaylist.id } })}>
            <span className="insight-kicker">Layer 2</span>
            <strong>Listening Thread</strong>
            <p>Saved order, queue continuity, sequence logic.</p>
          </button>
          <button className="layer-card" onClick={() => navigate({ to: "/oracle" })}>
            <span className="insight-kicker">Layer 3</span>
            <strong>Oracle</strong>
            <p>Flow, chaos, discovery, and queue generation.</p>
          </button>
          <button className="layer-card" onClick={() => libraryTracks[0] && openDossier(libraryTracks[0].trackId)}>
            <span className="insight-kicker">Layer 4</span>
            <strong>Dossier</strong>
            <p>Structure, lineage, samples, and track reasoning.</p>
          </button>
        </div>
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
