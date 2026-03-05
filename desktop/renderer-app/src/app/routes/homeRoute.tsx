import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryTracks, getOracleRecommendations, getPlaylistDetail, getPlaylists } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPill } from "@/ui/LyraPill";

export function HomeRoute() {
  const navigate = useNavigate();
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });
  const { data: recommendations = [] } = useQuery({ queryKey: ["oracle", "home"], queryFn: () => getOracleRecommendations("flow") });
  const { data: library } = useQuery({ queryKey: ["home-library"], queryFn: () => getLibraryTracks(10, 0, "") });
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
            <h2>Current Thread</h2>
            <span>{queue.items.length} queued</span>
          </div>
          <div className="compact-list">
            <button className="thread-row" onClick={() => currentTrack && openDossier(currentTrack.trackId)}>
              <div>
                <strong>{currentTrack?.title ?? "No active track"}</strong>
                <p>{currentTrack ? `${currentTrack.artist} | ${currentTrack.album ?? "Single"}` : "Start from library, thread, or Auto-DJ."}</p>
                {player.currentTimeSec > 0 && player.durationSec > 0 && (
                  <p>Resume from {Math.round(player.currentTimeSec)}s of {Math.round(player.durationSec)}s</p>
                )}
              </div>
              <span>{player.status}</span>
            </button>
            {queue.items.slice(queue.currentIndex + 1, queue.currentIndex + 4).map((track, index) => (
              <button
                key={`${track.trackId}-${index}`}
                className="thread-row"
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
                <span>Next</span>
              </button>
            ))}
          </div>
          <div className="hero-actions">
            <LyraButton onClick={() => currentTrack && void audioEngine.playTrack(currentTrack)} disabled={!currentTrack}>Resume</LyraButton>
            <LyraButton onClick={() => navigate({ to: "/queue" })}>Open queue</LyraButton>
          </div>
        </section>

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
                onClick={() => {
                  replaceQueue({
                    queueId: `home-library-${track.trackId}`,
                    origin: "home-library",
                    reorderable: true,
                    currentIndex: 0,
                    items: [track],
                  });
                  void audioEngine.playTrack(track);
                }}
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

    </div>
  );
}
