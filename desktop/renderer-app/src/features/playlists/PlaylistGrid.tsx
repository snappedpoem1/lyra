import type { PlaylistSummary } from "@/types/domain";
import { PlaylistCard } from "@/features/playlists/PlaylistCard";

export function PlaylistGrid({ playlists }: { playlists: PlaylistSummary[] }) {
  return (
    <div className="playlist-grid">
      {playlists.map((playlist) => (
        <PlaylistCard key={playlist.id} playlist={playlist} />
      ))}
    </div>
  );
}
