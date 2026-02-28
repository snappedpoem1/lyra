import { Link } from "@tanstack/react-router";
import type { PlaylistSummary } from "@/types/domain";

export function PlaylistGrid({ playlists }: { playlists: PlaylistSummary[] }) {
  return (
    <div className="compact-list playlist-list">
      {playlists.map((playlist) => (
        <Link key={playlist.id} to="/playlists/$playlistId" params={{ playlistId: playlist.id }} className="thread-row playlist-row">
          <div>
            <strong>{playlist.title}</strong>
            <p>{playlist.subtitle}</p>
          </div>
          <span>{playlist.trackCount}</span>
        </Link>
      ))}
    </div>
  );
}
