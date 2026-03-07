import { useState } from "react";
import { ActionIcon, Button, Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { deletePlaylist, getSavedPlaylists, playPlaylist } from "@/services/lyraGateway/queries";
import { LyraPanel } from "@/ui/LyraPanel";
import { CreatePlaylistModal } from "./CreatePlaylistModal";

export function SavedPlaylistsSection() {
  const [modalOpen, setModalOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: playlists = [], isLoading, error } = useQuery({
    queryKey: ["saved-playlists"],
    queryFn: getSavedPlaylists,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePlaylist(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["saved-playlists"] }),
  });

  const playMutation = useMutation({
    mutationFn: (id: string) => playPlaylist(id),
  });

  if (error) return null;

  return (
    <LyraPanel className="saved-playlists-section">
      <Group justify="space-between" className="section-heading">
        <div>
          <h2>Saved playlists</h2>
          <span>{playlists.length} {playlists.length === 1 ? "playlist" : "playlists"}</span>
        </div>
        <Button size="xs" variant="light" onClick={() => setModalOpen(true)}>
          + New playlist
        </Button>
      </Group>

      {isLoading && <Text size="sm" c="dimmed">Loading…</Text>}

      {!isLoading && playlists.length === 0 && (
        <Text size="sm" c="dimmed">No saved playlists yet. Create one to get started.</Text>
      )}

      {playlists.length > 0 && (
        <ul className="saved-playlists-list">
          {playlists.map((pl) => (
            <li key={pl.id} className="saved-playlist-row">
              <Link to="/playlists/$playlistId" params={{ playlistId: pl.id }} className="saved-playlist-name">
                <strong>{pl.name}</strong>
                {pl.description && <span className="saved-playlist-desc">{pl.description}</span>}
              </Link>
              <span className="saved-playlist-count">{pl.track_count} tracks</span>
              <Group gap={4} className="saved-playlist-actions">
                <ActionIcon
                  size="sm"
                  variant="subtle"
                  title="Play"
                  onClick={() => playMutation.mutate(pl.id)}
                  loading={playMutation.isPending && playMutation.variables === pl.id}
                >
                  ▶
                </ActionIcon>
                <ActionIcon
                  size="sm"
                  variant="subtle"
                  color="red"
                  title="Delete"
                  onClick={() => deleteMutation.mutate(pl.id)}
                  loading={deleteMutation.isPending && deleteMutation.variables === pl.id}
                >
                  ✕
                </ActionIcon>
              </Group>
            </li>
          ))}
        </ul>
      )}

      <CreatePlaylistModal opened={modalOpen} onClose={() => setModalOpen(false)} />
    </LyraPanel>
  );
}
