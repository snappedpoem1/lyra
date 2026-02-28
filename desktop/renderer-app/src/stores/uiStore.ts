import { create } from "zustand";
import type { RightRailTab } from "@/types/domain";

interface UiStore {
  rightRailTab: RightRailTab;
  commandPaletteOpen: boolean;
  searchOverlayOpen: boolean;
  dossierTrackId: string | null;
  setRightRailTab: (tab: RightRailTab) => void;
  toggleCommandPalette: (next?: boolean) => void;
  toggleSearchOverlay: (next?: boolean) => void;
  openDossier: (trackId: string) => void;
  closeDossier: () => void;
}

export const useUiStore = create<UiStore>((set, get) => ({
  rightRailTab: "now-playing",
  commandPaletteOpen: false,
  searchOverlayOpen: false,
  dossierTrackId: null,
  setRightRailTab: (tab) => set({ rightRailTab: tab }),
  toggleCommandPalette: (next) => set({ commandPaletteOpen: next ?? !get().commandPaletteOpen }),
  toggleSearchOverlay: (next) => set({ searchOverlayOpen: next ?? !get().searchOverlayOpen }),
  openDossier: (trackId) => set({ dossierTrackId: trackId, rightRailTab: "details" }),
  closeDossier: () => set({ dossierTrackId: null }),
}));
