import { useState } from "react";
import { Button, Modal, Stack, Textarea, TextInput } from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createPlaylist } from "@/services/lyraGateway/queries";

interface Props {
  opened: boolean;
  onClose: () => void;
}

export function CreatePlaylistModal({ opened, onClose }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createPlaylist(name.trim(), description.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["saved-playlists"] });
      setName("");
      setDescription("");
      onClose();
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim()) mutation.mutate();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New playlist" centered>
      <form onSubmit={handleSubmit}>
        <Stack gap="sm">
          <TextInput
            label="Name"
            placeholder="Give it a name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            required
            autoFocus
          />
          <Textarea
            label="Description"
            placeholder="What is this for? (optional)"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            autosize
            minRows={2}
          />
          <Button
            type="submit"
            loading={mutation.isPending}
            disabled={!name.trim()}
            fullWidth
          >
            Create
          </Button>
          {mutation.isError && (
            <p className="form-error">Could not create playlist. Try again.</p>
          )}
        </Stack>
      </form>
    </Modal>
  );
}
