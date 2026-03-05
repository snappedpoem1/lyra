import { Link } from "@tanstack/react-router";
import type { PlaylistSummary } from "@/types/domain";

function hue(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
}

function PlaylistMosaic({ items, size = 48 }: { items: string[]; size?: number }) {
  // Up to 4 colour squares derived from track strings (or title-derived if empty)
  const squares = [...items].slice(0, 4);
  while (squares.length < 4) squares.push(String(squares.length));
  return (
    <div
      className="playlist-mosaic"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {squares.map((s, i) => {
        const h = hue(s);
        return (
          <div
            key={i}
            className="playlist-mosaic-cell"
            style={{ background: `hsl(${h},32%,20%)` }}
          />
        );
      })}
    </div>
  );
}

export function PlaylistGrid({ playlists }: { playlists: PlaylistSummary[] }) {
  return (
    <div className="playlist-cards">
      {playlists.map((playlist) => (
        <Link
          key={playlist.id}
          to="/playlists/$playlistId"
          params={{ playlistId: playlist.id }}
          className="playlist-card"
        >
          <PlaylistMosaic items={playlist.coverMosaic ?? [playlist.title]} />
          <div className="playlist-card-body">
            <strong className="playlist-card-title">{playlist.title}</strong>
            <p className="playlist-card-sub">{playlist.subtitle}</p>
            <span className="playlist-card-count">{playlist.trackCount} tracks</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

export { PlaylistMosaic };
