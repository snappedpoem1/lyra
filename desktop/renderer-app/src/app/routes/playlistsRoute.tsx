import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { PlaylistGrid } from "@/features/playlists/PlaylistGrid";
import { LyraPanel } from "@/ui/LyraPanel";

export function PlaylistsRoute() {
  const { data: playlists = [], error } = useQuery({ queryKey: ["playlists"], queryFn: getPlaylists });

  return (
    <div className="route-stack">
      <LyraPanel className="playlists-stage-hero">
        <div className="playlists-stage-copy">
          <span className="hero-kicker">Saved Threads</span>
          <Title order={1}>Reusable listening sequences cut from the live library.</Title>
          <Text className="playlists-stage-summary">
            These are the paths worth revisiting: guided arcs, useful pivots, and
            stable sequence objects you can drop back into the queue immediately.
          </Text>
        </div>
        <Group gap="xs" className="playlists-stage-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {playlists.length} threads
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            Library-backed
          </Badge>
        </Group>
      </LyraPanel>
      {error && (
        <LyraPanel className="empty-state-panel">
          Backend unavailable. Playlists are not live right now.
        </LyraPanel>
      )}
      <PlaylistGrid playlists={playlists} />
    </div>
  );
}
