import { useQuery } from "@tanstack/react-query";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { PlaylistGrid } from "@/features/playlists/PlaylistGrid";

export function PlaylistsRoute() {
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Playlists</span>
        <h1>Your saved vibes and curated sets</h1>
      </section>
      <PlaylistGrid playlists={playlists} />
    </div>
  );
}
