import { useQuery } from "@tanstack/react-query";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { PlaylistGrid } from "@/features/playlists/PlaylistGrid";

export function PlaylistsRoute() {
  const { data: playlists = [] } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Playlists first</span>
        <h1>Curated arcs, not folders with delusions.</h1>
      </section>
      <PlaylistGrid playlists={playlists} />
    </div>
  );
}
