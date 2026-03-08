import { Link } from "@tanstack/react-router";
import type { PlaylistSummary } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraPill } from "@/ui/LyraPill";

export function PlaylistCard({ playlist }: { playlist: PlaylistSummary }) {
  return (
    <Link to="/playlists/$playlistId" params={{ playlistId: playlist.id }}>
      <LyraPanel className="playlist-card">
        <div className="card-mosaic">
          {playlist.coverMosaic.map((letter, index) => (
            <span key={`${playlist.id}-${index}`}>{letter}</span>
          ))}
        </div>
        <div className="section-heading">
          <h3>{playlist.title}</h3>
          <LyraPill>{playlist.trackCount} tracks</LyraPill>
        </div>
        <p>{playlist.subtitle}</p>
        <p className="card-narrative">{playlist.narrative}</p>
      </LyraPanel>
    </Link>
  );
}
