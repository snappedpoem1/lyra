import { Badge, Group, Text, Title } from "@mantine/core";
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
import { usePlayerStore } from "@/stores/playerStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function PlaylistDetailRoute() {
  const { playlistId } = useParams({ strict: false });
  const navigate = useNavigate();
  const { data: detail } = useQuery({
    queryKey: ["playlist-detail", playlistId],
    queryFn: () => getPlaylistDetail(playlistId ?? "after-midnight-ritual"),
  });
  const { data: constellation, error: constellationError } = useQuery({ queryKey: ["constellation"], queryFn: () => getConstellation() });
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);
  const constellationNodeCount = constellation?.nodes.length ?? 0;

  if (!detail) {
    return null;
  }

  return (
    <div className="route-stack">
      <LyraPanel className="playlist-archive-hero">
        <div className="playlist-archive-copy">
          <span className="hero-kicker">Listening Thread</span>
          <Title order={1}>{detail.summary.title}</Title>
          <Text className="playlist-archive-summary">
            {detail.summary.narrative}
          </Text>
        </div>
        <Group gap="xs" className="playlist-archive-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {detail.summary.trackCount} tracks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {detail.oraclePivots.length} oracle pivots
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {detail.relatedPlaylists.length} related threads
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
            {detail.summary.freshnessLabel}
          </Badge>
        </Group>
      </LyraPanel>

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

      <section className="playlist-archive-strip">
        <LyraPanel className="playlist-archive-signal-card">
          <span className="insight-kicker">Thread condition</span>
          <strong>{detail.summary.lastTouchedLabel ?? "Tonight"}</strong>
          <p>Saved as a reusable route through the current library state.</p>
        </LyraPanel>
        <LyraPanel className="playlist-archive-signal-card">
          <span className="insight-kicker">Emotional markers</span>
          <strong>{detail.summary.emotionalSignature.length} active tags</strong>
          <p>{detail.summary.emotionalSignature.map((chip) => chip.key).join(" / ")}</p>
        </LyraPanel>
        <LyraPanel className="playlist-archive-signal-card">
          <span className="insight-kicker">Graph context</span>
          <strong>{constellationNodeCount} constellation nodes</strong>
          <p>{constellationNodeCount ? "Nearby graph context is available for pivots." : "Graph context will appear when the backend provides it."}</p>
        </LyraPanel>
      </section>

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
          <TrackTable tracks={detail.tracks} onPlayTrack={(track) => {
            setCurrentTrack(track.trackId);
            setTrack(track, detail.summary.title, track.reason);
            void audioEngine.playTrack(track);
          }} />
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

      {constellationError ? (
        <section className="lyra-panel empty-state-panel">
          <h2>Constellation unavailable</h2>
          <p>{constellationError instanceof Error ? constellationError.message : "The constellation backend did not respond."}</p>
        </section>
      ) : constellation ? (
        <section className="playlist-archive-section">
          <div className="section-heading">
            <h2>Constellation bridge</h2>
            <span>{constellation.nodes.length} nodes / {constellation.edges.length} edges</span>
          </div>
          <ConstellationScene
            nodes={constellation.nodes}
            edges={constellation.edges}
            onSelectNode={() => navigate({ to: "/oracle" })}
          />
        </section>
      ) : null}
    </div>
  );
}
