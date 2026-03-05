import { useNavigate } from "@tanstack/react-router";
import type { LibraryAlbumDetail, LibraryArtistDetail, TrackListItem } from "@/types/domain";
import { useUiStore } from "@/stores/uiStore";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";
import { ContextMenu } from "@/ui/ContextMenu";
import { useContextMenu } from "@/ui/useContextMenu";

function formatDuration(sec?: number | null): string {
  if (!sec || !isFinite(sec) || sec <= 0) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function TrackArtCell({ title }: { title: string }) {
  const letter = title.trim()[0]?.toUpperCase() ?? "?";
  const hue = letter.charCodeAt(0) * 37 % 360;
  return (
    <div className="track-art-cell">
      <div
        className="track-art-placeholder"
        style={{
          "--art-bg":   `hsl(${hue},28%,18%)`,
          "--art-text": `hsl(${hue},55%,72%)`,
        } as React.CSSProperties}
      >
        {letter}
      </div>
    </div>
  );
}

function TrackRowWithMenu({
  track,
  onPlay,
  onQueue,
  onDossier,
  onArtist,
}: {
  track: TrackListItem;
  onPlay: () => void;
  onQueue: () => void;
  onDossier: () => void;
  onArtist: () => void;
}) {
  const { menu, open, close } = useContextMenu();

  const menuItems = [
    { label: "Play now",          icon: "▶", action: onPlay    },
    { label: "Add to queue",      icon: "+", action: onQueue   },
    { label: "Track info",        icon: "◉", action: onDossier },
    { label: `Artist: ${track.artist}`, icon: "⊙", action: onArtist },
    {
      label: "Copy file path",    icon: "⊕",
      action: () => {
        if (track.path) void navigator.clipboard.writeText(track.path);
      },
    },
  ];

  return (
    <>
      <div
        className="track-row"
        onContextMenu={open}
      >
        <TrackArtCell title={track.title} />
        <div className="track-meta">
          <strong>{track.title}</strong>
          <span>{track.artist}{track.album ? ` · ${track.album}` : ""}</span>
        </div>
        <div className="track-reason">{track.reason}</div>
        <div className="track-duration">{formatDuration(track.durationSec)}</div>
        <div className="track-actions">
          <LyraButton onClick={onPlay}>Play</LyraButton>
          <LyraButton onClick={onQueue}>Queue</LyraButton>
          <LyraButton onClick={onDossier}>Info</LyraButton>
        </div>
      </div>
      {menu && (
        <ContextMenu x={menu.x} y={menu.y} items={menuItems} onClose={close} />
      )}
    </>
  );
}

export function LibraryOmensPanel({
  tracks,
  total,
  query,
  selectedArtist,
  selectedAlbum,
  artistOptions,
  albumOptions,
  onSelectArtist,
  onSelectAlbum,
  onClearFilters,
  artistDetail,
  albumDetail,
  onPlayFocusedSlice,
  onQueueFocusedSlice,
  onQueryChange,
  onPlayTrack,
  onQueueTrack,
  sortKey,
  sortDir,
  onSortChange,
  onPrevPage,
  onNextPage,
  hasPrevPage,
  hasNextPage,
}: {
  tracks: TrackListItem[];
  total: number;
  query: string;
  selectedArtist: string | null;
  selectedAlbum: string | null;
  artistOptions: Array<{ name: string; count: number }>;
  albumOptions: Array<{ name: string; count: number }>;
  onSelectArtist: (value: string | null) => void;
  onSelectAlbum: (value: string | null) => void;
  onClearFilters: () => void;
  artistDetail?: LibraryArtistDetail;
  albumDetail?: LibraryAlbumDetail;
  onPlayFocusedSlice: () => void;
  onQueueFocusedSlice: () => void;
  onQueryChange: (value: string) => void;
  onPlayTrack: (track: TrackListItem) => void;
  onQueueTrack: (track: TrackListItem) => void;
  sortKey: "title" | "artist" | "album";
  sortDir: "asc" | "desc";
  onSortChange: (value: "title" | "artist" | "album") => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  hasPrevPage: boolean;
  hasNextPage: boolean;
}) {
  const openDossier = useUiStore((state) => state.openDossier);
  const navigate    = useNavigate();

  const headline = albumDetail
    ? {
        title:    albumDetail.album,
        subtitle: `${albumDetail.artist} | ${albumDetail.trackCount} tracks`,
        meta:     albumDetail.years.join(", ") || "Album slice",
      }
    : artistDetail
      ? {
          title:    artistDetail.artist,
          subtitle: `${artistDetail.trackCount} tracks across ${artistDetail.albumCount} albums`,
          meta:     artistDetail.years.join(", ") || "Artist slice",
        }
      : null;

  return (
    <LyraPanel className="library-panel">
      <div className="section-heading">
        <h2>Library</h2>
        <span>{total} indexed tracks</span>
      </div>
      <div className="library-toolbar">
        <input
          className="command-input"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Filter by artist, title, or album"
        />
        <div className="sort-segmented">
          {(["artist", "album", "title"] as const).map((key) => (
            <button
              key={key}
              className={`sort-seg-btn${sortKey === key ? " is-active" : ""}`}
              onClick={() => onSortChange(key)}
            >
              {key}{sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
            </button>
          ))}
          <button className="sort-seg-btn" onClick={onClearFilters}>Reset</button>
        </div>
      </div>
      <div className="library-browser">
        <div className="library-browser-nav">
          <div className="library-nav-section">
            <span className="insight-kicker">Artists</span>
            <div className="compact-list">
              <button className={`thread-row ${selectedArtist === null ? "is-selected" : ""}`} onClick={() => onSelectArtist(null)}>
                <div>
                  <strong>All artists</strong>
                  <p>Current result page</p>
                </div>
                <span>{artistOptions.length}</span>
              </button>
              {artistOptions.map((artist) => (
                <button
                  key={artist.name}
                  className={`thread-row ${selectedArtist === artist.name ? "is-selected" : ""}`}
                  onClick={() => onSelectArtist(artist.name)}
                >
                  <div>
                    <strong>{artist.name}</strong>
                    <p>{artist.count} matching tracks</p>
                  </div>
                  <span>Artist</span>
                </button>
              ))}
            </div>
          </div>
          <div className="library-nav-section">
            <span className="insight-kicker">Albums</span>
            <div className="compact-list">
              <button className={`thread-row ${selectedAlbum === null ? "is-selected" : ""}`} onClick={() => onSelectAlbum(null)}>
                <div>
                  <strong>All albums</strong>
                  <p>{selectedArtist ?? "All artists"}</p>
                </div>
                <span>{albumOptions.length}</span>
              </button>
              {albumOptions.map((album) => (
                <button
                  key={album.name}
                  className={`thread-row ${selectedAlbum === album.name ? "is-selected" : ""}`}
                  onClick={() => onSelectAlbum(album.name)}
                >
                  <div>
                    <strong>{album.name}</strong>
                    <p>{album.count} matching tracks</p>
                  </div>
                  <span>Album</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="library-browser-main">
          {headline && (
            <div className="library-focus-card">
              <div>
                <span className="insight-kicker">{albumDetail ? "Album" : "Artist"}</span>
                <h3>{headline.title}</h3>
                <p>{headline.subtitle}</p>
                <p>{headline.meta}</p>
              </div>
              <div className="hero-actions">
                <LyraButton onClick={onPlayFocusedSlice}>Play slice</LyraButton>
                <LyraButton onClick={onQueueFocusedSlice}>Queue slice</LyraButton>
              </div>
            </div>
          )}
          <div className="library-header-row">
            <span />
            <span>Track</span>
            <span>Context</span>
            <span>Dur</span>
            <span>Actions</span>
          </div>
          <div className="track-rows">
            {tracks.map((track) => (
              <TrackRowWithMenu
                key={track.trackId}
                track={track}
                onPlay={() => onPlayTrack(track)}
                onQueue={() => onQueueTrack(track)}
                onDossier={() => openDossier(track.trackId)}
                onArtist={() => navigate({ to: "/artist/$name", params: { name: track.artist } })}
              />
            ))}
            {!tracks.length && <p className="text-dim">No tracks matched this filter.</p>}
          </div>
          <div className="library-pagination">
            <LyraButton onClick={onPrevPage} disabled={!hasPrevPage}>Prev</LyraButton>
            <span className="library-page-count">{total} tracks</span>
            <LyraButton onClick={onNextPage} disabled={!hasNextPage}>Next</LyraButton>
          </div>
        </div>
      </div>
    </LyraPanel>
  );
}
