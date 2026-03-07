import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { audioEngine } from "@/services/audio/audioEngine";
import {
  getAgentBriefing,
  getLibraryTracks,
  getOracleRecommendations,
  getPlaylistDetail,
  getPlaylists,
} from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function HomeRoute() {
  const navigate = useNavigate();
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });
  const { data: recommendations = [] } = useQuery({
    queryKey: ["oracle", "home"],
    queryFn: () => getOracleRecommendations("flow"),
  });
  const { data: library } = useQuery({
    queryKey: ["home-library"],
    queryFn: () => getLibraryTracks(10, 0, ""),
  });
  const { data: briefing } = useQuery({
    queryKey: ["agent", "briefing"],
    queryFn: getAgentBriefing,
    staleTime: 5 * 60 * 1000,
  });

  const player = usePlayerStore();
  const queue = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const openDossier = useUiStore((state) => state.openDossier);

  const leadPlaylist = playlists[0];
  const secondaryPlaylist = playlists[1];
  const libraryTracks = library?.tracks ?? [];
  const currentTrack = player.track ?? queue.items[queue.currentIndex] ?? null;

  const playLead = async () => {
    if (!leadPlaylist) {
      return;
    }
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

  const queueSingleTrack = async (
    queueId: string,
    origin: string,
    trackIndex: number,
  ) => {
    const track = libraryTracks[trackIndex];
    if (!track) {
      return;
    }
    replaceQueue({
      queueId,
      origin,
      reorderable: true,
      currentIndex: 0,
      items: [track],
    });
    await audioEngine.playTrack(track);
  };

  return (
    <div className="route-stack">
      <LyraPanel className="home-studio-hero">
        <div className="home-studio-hero-copy">
          <span className="hero-kicker">Lyra Music</span>
          <Title order={1}>A local-first listening desk with memory, queue, and instinct.</Title>
          <Text className="home-studio-summary">
            Move between saved threads, direct library pulls, and Oracle pivots without
            dropping into tool mode. The shell stays focused on what you can play next.
          </Text>
        </div>
        <Group gap="xs" className="home-studio-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
            <ConnectivityBadge />
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {library?.total ?? 0} tracks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {playlists.length} threads
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {queue.items.length} queued
          </Badge>
        </Group>
      </LyraPanel>

      <section className="home-studio-grid">
        <LyraPanel className="home-studio-card home-studio-card--feature">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Current Thread</span>
              <h2>{currentTrack?.title ?? "No active track"}</h2>
            </div>
            <span className="home-card-meta">{player.status}</span>
          </div>
          <p className="home-card-body-copy">
            {currentTrack
              ? `${currentTrack.artist} / ${currentTrack.album ?? "Single"}`
              : "Start from the queue, a saved thread, or a direct library jump."}
          </p>
          {player.currentTimeSec > 0 && player.durationSec > 0 ? (
            <div className="home-progress-chip">
              Resume from {Math.round(player.currentTimeSec)}s of {Math.round(player.durationSec)}s
            </div>
          ) : null}
          <div className="home-studio-list">
            {queue.items.slice(queue.currentIndex + 1, queue.currentIndex + 4).map((track, index) => (
              <button
                key={`${track.trackId}-${index}`}
                type="button"
                className="home-thread-card"
                onClick={() => {
                  const nextIndex = queue.items.findIndex((item) => item.trackId === track.trackId);
                  setCurrentIndex(nextIndex);
                  void audioEngine.playTrack(track);
                }}
              >
                <div>
                  <strong>{track.title}</strong>
                  <p>{track.artist}</p>
                </div>
                <span>Queue</span>
              </button>
            ))}
          </div>
          <div className="home-card-actions">
            <LyraButton
              className="lyra-button--accent"
              onClick={() => currentTrack && void audioEngine.playTrack(currentTrack)}
              disabled={!currentTrack}
            >
              Resume
            </LyraButton>
            <LyraButton
              onClick={() => currentTrack && openDossier(currentTrack.trackId)}
              disabled={!currentTrack}
            >
              Dossier
            </LyraButton>
            <LyraButton onClick={() => navigate({ to: "/queue" })}>Open queue</LyraButton>
          </div>
        </LyraPanel>

        <LyraPanel className="home-studio-card">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Saved Threads</span>
              <h2>Reusable sequences</h2>
            </div>
            <span className="home-card-meta">{playlists.length} total</span>
          </div>
          <div className="home-studio-list">
            {playlists.slice(0, 6).map((playlist) => (
              <button
                key={playlist.id}
                type="button"
                className="home-thread-card"
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
          <div className="home-card-actions">
            <LyraButton className="lyra-button--accent" onClick={() => void playLead()} disabled={!leadPlaylist}>
              Play lead
            </LyraButton>
            <LyraButton onClick={() => navigate({ to: "/playlists" })}>Open threads</LyraButton>
          </div>
        </LyraPanel>

        <LyraPanel className="home-studio-card">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Library Jump</span>
              <h2>Immediate pulls</h2>
            </div>
            <span className="home-card-meta">Direct play</span>
          </div>
          <div className="home-studio-list">
            {libraryTracks.map((track, index) => (
              <button
                key={track.trackId}
                type="button"
                className="home-thread-card"
                onClick={() => void queueSingleTrack(`home-library-${track.trackId}`, "home-library", index)}
              >
                <div>
                  <strong>{track.title}</strong>
                  <p>{track.artist} / {track.album ?? "Single"}</p>
                </div>
                <span>{track.durationSec ? `${Math.round(track.durationSec)}s` : "--"}</span>
              </button>
            ))}
          </div>
          <div className="home-card-actions">
            <LyraButton onClick={() => navigate({ to: "/library" })}>Open library</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/search" })}>Search library</LyraButton>
          </div>
        </LyraPanel>

        <LyraPanel className="home-studio-card">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Oracle Signal</span>
              <h2>What the system sees</h2>
            </div>
            <span className="home-card-meta">
              {briefing?.library_total ?? 0} tracks / {briefing?.playback_total ?? 0} plays
            </span>
          </div>
          <div className="home-signal-strip">
            {briefing?.newest_tracks?.slice(0, 3).map((track, index) => (
              <div key={`new-${index}`} className="home-signal-card">
                <span className="insight-kicker">Recently added</span>
                <strong>{track.title}</strong>
                <p>{track.artist}</p>
              </div>
            ))}
            {briefing?.top_queue_items?.slice(0, 3).map((item, index) => (
              <div key={`queue-${index}`} className="home-signal-card">
                <span className="insight-kicker">Taste-aligned</span>
                <strong>{item.title}</strong>
                <p>{item.artist}</p>
              </div>
            ))}
            {briefing?.taste_snapshot && Object.keys(briefing.taste_snapshot).length > 0 ? (
              <div className="home-signal-card home-signal-card--wide">
                <span className="insight-kicker">Top dimensions</span>
                <p>
                  {Object.entries(briefing.taste_snapshot)
                    .sort((a, b) => b[1].confidence - a[1].confidence)
                    .slice(0, 3)
                    .map(([dimension, payload]) => `${dimension} ${(payload.value * 100).toFixed(0)}%`)
                    .join(" / ")}
                </p>
              </div>
            ) : null}
          </div>
          <div className="home-card-actions">
            <LyraButton onClick={() => navigate({ to: "/oracle" })}>Open Oracle</LyraButton>
          </div>
        </LyraPanel>

        <LyraPanel className="home-studio-card home-studio-card--wide">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Auto-DJ Moves</span>
              <h2>Controlled pivots</h2>
            </div>
            <span className="home-card-meta">{recommendations.length} live moves</span>
          </div>
          <div className="home-recommendation-grid">
            {recommendations.map((item) => (
              <button
                key={item.id}
                type="button"
                className="home-recommendation-card"
                onClick={() => {
                  const firstTrack = item.previewTracks[0];
                  replaceQueue({
                    queueId: item.id,
                    origin: "home",
                    reorderable: true,
                    currentIndex: 0,
                    items: item.previewTracks,
                  });
                  if (firstTrack) {
                    void audioEngine.playTrack(firstTrack);
                  }
                }}
              >
                <span className="insight-kicker">{item.mode}</span>
                <strong>{item.title}</strong>
                <p>{item.rationale}</p>
                <span>{item.previewTracks.length} track preview</span>
              </button>
            ))}
          </div>
          <div className="home-card-actions">
            <LyraButton className="lyra-button--accent" onClick={() => navigate({ to: "/oracle" })}>
              Open Auto-DJ
            </LyraButton>
            <LyraButton
              onClick={() =>
                secondaryPlaylist &&
                navigate({ to: "/playlists/$playlistId", params: { playlistId: secondaryPlaylist.id } })
              }
              disabled={!secondaryPlaylist}
            >
              Adjacent thread
            </LyraButton>
          </div>
        </LyraPanel>
      </section>
    </div>
  );
}
