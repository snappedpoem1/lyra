import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryArtistDetail, getLibraryArtistBio } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { usePlayerStore } from "@/stores/playerStore";
import { Icon } from "@/ui/Icon";
import { LyraButton } from "@/ui/LyraButton";
import type { TrackListItem } from "@/types/domain";

/** Hue derived from artist name — consistent per-artist color */
function artistHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

function ArtistAvatar({ name, size = 90 }: { name: string; size?: number }) {
  const hue = artistHue(name);
  const letter = name.trim()[0]?.toUpperCase() ?? "?";
  return (
    <div
      className="artist-avatar"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(145deg, hsl(${hue},38%,20%), hsl(${(hue + 50) % 360},46%,32%))`,
        color: `hsl(${hue},55%,82%)`,
        border: `2px solid hsl(${hue},30%,35%)`,
        boxShadow: `0 0 32px hsl(${hue},38%,20%)`,
      }}
      aria-hidden="true"
    >
      {letter}
    </div>
  );
}

function TrackRow({
  track,
  index,
  onPlay,
}: {
  track: TrackListItem;
  index: number;
  onPlay: (track: TrackListItem) => void;
}) {
  return (
    <div
      className="track-row artist-track-row"
      onClick={() => onPlay(track)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onPlay(track)}
    >
      <span className="track-row-index">{index + 1}</span>
      <div className="track-row-main">
        <span className="track-row-title">{track.title}</span>
        <span className="track-row-album">{track.album ?? ""}</span>
      </div>
      <span className="track-row-action">
        <Icon name="play" className="inline-icon" />
      </span>
    </div>
  );
}

export function ArtistRoute() {
  const { name } = useParams({ from: "/artist/$name" });
  const navigate = useNavigate();
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);

  const { data: detail, isLoading } = useQuery({
    queryKey: ["artist-detail", name],
    queryFn: () => getLibraryArtistDetail(name),
    enabled: Boolean(name),
  });

  const { data: bio } = useQuery({
    queryKey: ["artist-bio", name],
    queryFn: () => getLibraryArtistBio(name),
    enabled: Boolean(name),
    retry: false,
  });

  const tracks: TrackListItem[] = detail?.tracks ?? [];
  const albums = detail?.albums ?? [];
  const years = detail?.years ?? [];

  const playAll = async () => {
    if (!tracks.length) return;
    replaceQueue({
      queueId: `artist-${name}`,
      origin: name,
      reorderable: true,
      currentIndex: 0,
      items: tracks,
    });
    setCurrentTrack(tracks[0].trackId);
    setTrack(tracks[0], name, undefined);
    await audioEngine.playTrack(tracks[0]);
  };

  const playTrack = async (track: TrackListItem) => {
    const idx = tracks.findIndex((t) => t.trackId === track.trackId);
    replaceQueue({
      queueId: `artist-${name}`,
      origin: name,
      reorderable: true,
      currentIndex: Math.max(0, idx),
      items: tracks,
    });
    setCurrentTrack(track.trackId);
    setTrack(track, name, undefined);
    await audioEngine.playTrack(track);
  };

  if (isLoading) {
    return (
      <div className="route-stack">
        <section className="lyra-panel empty-state-panel" style={{ padding: "28px" }}>
          Loading artist…
        </section>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="route-stack">
        <section className="lyra-panel empty-state-panel" style={{ padding: "28px" }}>
          <h2>Artist not found</h2>
          <p>"{name}" has no tracks in the library.</p>
          <LyraButton onClick={() => void navigate({ to: "/library" })}>
            Back to Library
          </LyraButton>
        </section>
      </div>
    );
  }

  const yearRange = years.length > 1
    ? `${years[0]} – ${years[years.length - 1]}`
    : years[0] ?? "";

  return (
    <div className="artist-page route-stack">
      {/* Hero */}
      <section className="lyra-panel artist-hero">
        <ArtistAvatar name={name} size={90} />
        <div>
          <div style={{ color: "var(--text-dim)", fontSize: "0.72rem", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 6 }}>
            Artist
          </div>
          <h1 style={{ margin: "0 0 10px", fontSize: "2rem", fontWeight: 700, lineHeight: 1.1 }}>{name}</h1>

          {bio?.bio && (
            <p className="artist-bio">{bio.bio}</p>
          )}

          <div className="artist-stats-row" style={{ marginBottom: 18 }}>
            <div className="artist-stat">
              <span className="artist-stat-value">{detail.trackCount}</span>
              <span className="artist-stat-label">Tracks</span>
            </div>
            <div className="artist-stat">
              <span className="artist-stat-value">{detail.albumCount}</span>
              <span className="artist-stat-label">Albums</span>
            </div>
            {yearRange && (
              <div className="artist-stat">
                <span className="artist-stat-value">{yearRange}</span>
                <span className="artist-stat-label">Years</span>
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <LyraButton onClick={() => void playAll()} disabled={!tracks.length}>
              <Icon name="play" className="inline-icon" /> Play All
            </LyraButton>
            <LyraButton onClick={() => void navigate({ to: "/library" })}>
              Library
            </LyraButton>
          </div>
        </div>
      </section>

      {/* Albums */}
      {albums.length > 0 && (
        <section className="lyra-panel" style={{ padding: "20px 24px" }}>
          <h3 style={{ margin: "0 0 16px", fontSize: "0.8rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-dim)" }}>
            Discography
          </h3>
          <div className="artist-albums-grid">
            {albums.map((album) => (
              <div key={album.name} className="artist-album-card" title={`${album.count} tracks`}>
                <div
                  style={{
                    width: "100%",
                    aspectRatio: "1",
                    borderRadius: 6,
                    background: `linear-gradient(145deg, hsl(${artistHue(album.name)},28%,18%), hsl(${(artistHue(album.name) + 60) % 360},36%,26%))`,
                    display: "grid",
                    placeItems: "center",
                    fontSize: "1.6rem",
                    marginBottom: 10,
                    color: `hsl(${artistHue(album.name)},60%,75%)`,
                  }}
                >
                  {album.name[0]?.toUpperCase()}
                </div>
                <div style={{ fontSize: "0.82rem", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {album.name}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-dim)", marginTop: 2 }}>
                  {album.count} track{album.count !== 1 ? "s" : ""}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Track list */}
      {tracks.length > 0 && (
        <section className="lyra-panel" style={{ padding: "20px 24px" }}>
          <h3 style={{ margin: "0 0 16px", fontSize: "0.8rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-dim)" }}>
            All Tracks
          </h3>
          <div className="track-rows">
            {tracks.map((track, i) => (
              <TrackRow key={track.trackId} track={track} index={i} onPlay={playTrack} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
