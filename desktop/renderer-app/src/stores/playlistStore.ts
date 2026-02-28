import { create } from "zustand";

interface PlaylistStore {
  activePlaylistId: string | null;
  selectedTrackId: string | null;
  setActivePlaylistId: (playlistId: string | null) => void;
  setSelectedTrackId: (trackId: string | null) => void;
}

export const usePlaylistStore = create<PlaylistStore>((set) => ({
  activePlaylistId: null,
  selectedTrackId: null,
  setActivePlaylistId: (activePlaylistId) => set({ activePlaylistId }),
  setSelectedTrackId: (selectedTrackId) => set({ selectedTrackId }),
}));
