import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryArtistDetail, getArtistShrine } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { usePlayerStore } from "@/stores/playerStore";
import { Icon } from "@/ui/Icon";
import { LyraButton } from "@/ui/LyraButton";
import type { TrackListItem } from "@/types/domain";

/** Hue derived from artist name â€” consistent per-artist color */
function artistHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

function ArtistAvatar({ name, thumbnail, size = 90 }: { name: string; thumbnail?: string; size?: number }) {
  const hue = artistHue(name);
  const letter = name.trim()[0]?.toUpperCase() ?? "?";
  if (thumbnail) {
    return (
      <img
        src={thumbnail}
        alt={name}
        className="artist-avatar artist-avatar--photo"
        style={{ width: size, height: size, objectFit: "cover", borderRadius: "50%", border: `2px solid hsl(${hue},30%,35%)` }}
      />
    );
  }
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

const SECTION_HEADER: React.CSSProperties = {
  margin: "0 0 16px",
  fontSize: "0.8rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "var(--text-dim)",
};

export function ArtistRoute() {
  const { name } = useParams({ from: "/artist/$name" });
  const navigate = useNavigate();
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);

  // Library detail: track list + album list + years
  const { data: detail, isLoading } = useQuery({
    queryKey: ["artist-detail", name],
    queryFn: () => getLibraryArtistDetail(name),
    enabled: Boolean(name),
  });

  // Shrine: bio, genres, origin, related artists, credits (runs in parallel)
  const { data: shrine } = useQuery({
    queryKey: ["artist-shrine", name],
    queryFn: () => getArtistShrine(name),
    enabled: Boolean(name),
    retry: false,
    staleTime: 10 * 60 * 1000,
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
          Loading artistâ€¦
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
    ? `${years[0]} â€“ ${years[years.length - 1]}`
    : years[0] ?? "";
  const hue = artistHue(name);

  // Credit groups to surface (exclude generic "other")
  const notableCredits = (shrine?.credits ?? []).filter(
    (c) => ["producer", "featured", "composer", "remixer", "lyricist", "mixer"].includes(c.role),
  );
  const creditsByRole = notableCredits.reduce<Record<string, typeof notableCredits>>(
    (acc, c) => { (acc[c.role] ??= []).push(c); return acc; },
    {},
  );

  return (
    <div className="artist-page route-stack">
      {/* Hero */}
      <section className="lyra-panel artist-hero">
        <ArtistAvatar name={name} thumbnail={shrine?.wikiThumbnail || undefined} size={90} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "var(--text-dim)", fontSize: "0.72rem", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 6 }}>
            Artist
          </div>
          <h1 style={{ margin: "0 0 6px", fontSize: "2rem", fontWeight: 700, lineHeight: 1.1 }}>{name}</h1>

          {/* Origin / scene tagline */}
          {(shrine?.origin || shrine?.era || shrine?.scene) && (
            <p style={{ margin: "0 0 8px", fontSize: "0.82rem", color: "var(--text-dim)" }}>
              {[shrine.origin, shrine.era, shrine.scene].filter(Boolean).join(" Â· ")}
            </p>
          )}

          {/* Genres */}
          {(shrine?.genres ?? []).length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 12 }}>
              {(shrine?.genres ?? []).slice(0, 8).map((g) => (
                <span key={g} style={{
                  background: `hsl(${hue},20%,18%)`,
                  border: `1px solid hsl(${hue},25%,30%)`,
                  color: `hsl(${hue},50%,72%)`,
                  borderRadius: 20,
                  padding: "2px 10px",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                }}>
                  {g}
                </span>
              ))}
            </div>
          )}

          {shrine?.bio && (
            <p className="artist-bio">{shrine.bio}</p>
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
            {shrine?.formationYear && (
              <div className="artist-stat">
                <span className="artist-stat-value">{shrine.formationYear}</span>
                <span className="artist-stat-label">Formed</span>
              </div>
            )}
            {shrine?.lastfmListeners != null && shrine.lastfmListeners > 0 && (
              <div className="artist-stat">
                <span className="artist-stat-value">
                  {shrine.lastfmListeners >= 1_000_000
                    ? `${(shrine.lastfmListeners / 1_000_000).toFixed(1)}M`
                    : shrine.lastfmListeners >= 1_000
                    ? `${(shrine.lastfmListeners / 1_000).toFixed(0)}K`
                    : String(shrine.lastfmListeners)}
                </span>
                <span className="artist-stat-label">Listeners</span>
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <LyraButton onClick={() => void playAll()} disabled={!tracks.length}>
              <Icon name="play" className="inline-icon" /> Play All
            </LyraButton>
            <LyraButton onClick={() => void navigate({ to: "/library" })}>
              Library
            </LyraButton>
            {shrine?.wikiUrl && (
              <a
                href={shrine.wikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--text-dim)", fontSize: "0.78rem", textDecoration: "none" }}
              >
                Wikipedia â†—
              </a>
            )}
          </div>
        </div>
      </section>

      {/* Related Artists */}
      {(shrine?.relatedArtists ?? []).length > 0 && (
        <section className="lyra-panel" style={{ padding: "18px 24px" }}>
          <h3 style={SECTION_HEADER}>Related Artists</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {(shrine?.relatedArtists ?? []).slice(0, 12).map((rel) => (
              <button
                key={rel.target}
                onClick={() => void navigate({ to: "/artist/$name", params: { name: rel.target } })}
                style={{
                  background: "var(--bg-soft)",
                  border: "1px solid var(--panel-border)",
                  borderRadius: 20,
                  color: "var(--text)",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  padding: "4px 14px",
                  transition: "background 0.15s, border-color 0.15s",
                }}
                title={rel.type}
              >
                {rel.target}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Notable Credits */}
      {Object.keys(creditsByRole).length > 0 && (
        <section className="lyra-panel" style={{ padding: "18px 24px" }}>
          <h3 style={SECTION_HEADER}>Credits</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {Object.entries(creditsByRole).map(([role, people]) => (
              <div key={role} style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-dim)", width: 80, flexShrink: 0, textTransform: "capitalize" }}>
                  {role}
                </span>
                <span style={{ fontSize: "0.82rem", color: "var(--text)" }}>
                  {people.map((p) => p.name).join(", ")}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Albums */}
      {albums.length > 0 && (
        <section className="lyra-panel" style={{ padding: "20px 24px" }}>
          <h3 style={SECTION_HEADER}>Discography</h3>
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
          <h3 style={SECTION_HEADER}>All Tracks</h3>
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
