import { useQuery } from "@tanstack/react-query";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { PlaylistGrid } from "@/features/playlists/PlaylistGrid";

export function PlaylistsRoute() {
  const { data: playlists = [], error } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Saved Threads</span>
        <h1>Reusable listening sequences from the live library</h1>
      </section>
      {error && <section className="lyra-panel">Backend unavailable. Playlists are not live right now.</section>}
      <PlaylistGrid playlists={playlists} />
    </div>
  );
}
