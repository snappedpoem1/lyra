import { create } from "zustand";
import type { NowPlayingState, TrackListItem, VisualizerFrame } from "@/types/domain";

interface PlayerStore extends NowPlayingState {
  frame: VisualizerFrame;
  errorMessage?: string;
  setTrack: (track: TrackListItem | null, sourceLabel?: string, explanation?: string) => void;
  setStatus: (status: NowPlayingState["status"]) => void;
  setError: (message: string) => void;
  setTime: (currentTimeSec: number, durationSec: number) => void;
  setVolume: (volume: number) => void;
  setMuted: (muted: boolean) => void;
  setVisualizerMode: (mode: NowPlayingState["visualizerMode"]) => void;
  setFrame: (frame: VisualizerFrame) => void;
}

export const usePlayerStore = create<PlayerStore>((set) => ({
  track: null,
  status: "idle",
  currentTimeSec: 0,
  durationSec: 0,
  progress: 0,
  volume: 0.82,
  muted: false,
  repeatMode: "off",
  shuffle: false,
  sourceLabel: undefined,
  explanation: undefined,
  visualizerMode: "bloom",
  frame: {
    waveform: new Array(64).fill(0),
    spectrum: new Array(48).fill(0),
    energy: 0.1,
    tension: 0.2,
    movement: 0.2,
    isPlaying: false,
  },
  errorMessage: undefined,
  setTrack: (track, sourceLabel, explanation) =>
    set({
      track,
      sourceLabel,
      explanation,
      errorMessage: undefined,
      currentTimeSec: 0,
      durationSec: track?.durationSec ?? 0,
      progress: 0,
      status: track ? "loading" : "idle",
    }),
  setStatus: (status) => set({ status }),
  setError: (errorMessage) => set({ status: "error", errorMessage }),
  setTime: (currentTimeSec, durationSec) =>
    set({
      currentTimeSec,
      durationSec,
      progress: durationSec > 0 ? currentTimeSec / durationSec : 0,
    }),
  setVolume: (volume) => set({ volume }),
  setMuted: (muted) => set({ muted }),
  setVisualizerMode: (visualizerMode) => set({ visualizerMode }),
  setFrame: (frame) => set({ frame }),
}));
