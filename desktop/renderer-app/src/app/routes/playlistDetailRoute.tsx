import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "@tanstack/react-router";
import { ConstellationScene } from "@/features/constellation/ConstellationScene";
import { EmotionalArcStrip } from "@/features/playlists/EmotionalArcStrip";
import { PlaylistHero } from "@/features/playlists/PlaylistHero";
import { PlaylistNarrative } from "@/features/playlists/PlaylistNarrative";
import { TrackTable } from "@/features/playlists/TrackTable";
import { audioEngine } from "@/services/audio/audioEngine";
import { getConstellation, getPlaylistDetail } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function PlaylistDetailRoute() {
  const { playlistId } = useParams({ strict: false });
  const navigate = useNavigate();
  const { data: detail } = useQuery({
    queryKey: ["playlist-detail", playlistId],
    queryFn: () => getPlaylistDetail(playlistId ?? "after-midnight-ritual"),
  });
  const { data: constellation } = useQuery({ queryKey: ["constellation"], queryFn: getConstellation });
  const replaceQueue = useQueueStore((state) => state.replaceQueue);

  if (!detail) {
    return null;
  }

  return (
    <div className="route-stack">
      <PlaylistHero
        detail={detail}
        onPlay={() => void audioEngine.playTrack(detail.tracks[0])}
        onQueue={() =>
          replaceQueue({
            queueId: detail.summary.id,
            origin: detail.summary.title,
            reorderable: true,
            currentIndex: 0,
            items: detail.tracks,
          })
        }
        onConstellation={() => navigate({ to: "/oracle" })}
      />

      <section className="playlist-focus-grid">
        <EmotionalArcStrip arc={detail.arc} />
        <LyraPanel className="playlist-focus-panel">
          <div className="section-heading">
            <h2>Sequence notes</h2>
            <span>Why this order</span>
          </div>
          <div className="playlist-focus-list">
            {detail.storyBeats.map((beat) => (
              <div key={beat} className="playlist-focus-row">
                <span className="insight-kicker">Note</span>
                <strong>{beat}</strong>
              </div>
            ))}
          </div>
        </LyraPanel>
      </section>

      <section className="playlist-detail-grid">
        <div className="playlist-detail-main">
          <PlaylistNarrative beats={detail.storyBeats} />
          <TrackTable tracks={detail.tracks} onPlayTrack={(track) => void audioEngine.playTrack(track)} />
        </div>
        <aside className="playlist-detail-side">
          <LyraPanel className="playlist-sidecar">
            <div className="section-heading">
              <h2>Recommendations</h2>
              <span>{detail.oraclePivots.length} suggestions</span>
            </div>
            {detail.oraclePivots.map((pivot) => (
              <div key={pivot.id} className="playlist-focus-row">
                <span className="insight-kicker">{pivot.mode}</span>
                <strong>{pivot.title}</strong>
                <p>{pivot.rationale}</p>
              </div>
            ))}
          </LyraPanel>
          <LyraPanel className="playlist-sidecar">
            <div className="section-heading">
              <h2>Related playlists</h2>
              <span>{detail.relatedPlaylists.length} similar</span>
            </div>
            {detail.relatedPlaylists.map((playlist) => (
              <button
                key={playlist.id}
                className="sanctuary-mini-card"
                onClick={() => navigate({ to: "/playlists/$playlistId", params: { playlistId: playlist.id } })}
              >
                <strong>{playlist.title}</strong>
                <p>{playlist.subtitle}</p>
              </button>
            ))}
          </LyraPanel>
        </aside>
      </section>

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
