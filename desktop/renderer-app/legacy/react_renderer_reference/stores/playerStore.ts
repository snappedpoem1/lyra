import { create } from "zustand";
import type { NowPlayingState, TrackListItem, VisualizerFrame } from "@/types/domain";

const STORAGE_KEY = "lyra-player";

type PlayerSnapshot = Pick<
  NowPlayingState,
  "track" | "currentTimeSec" | "durationSec" | "progress" | "volume" | "muted" | "sourceLabel" | "explanation" | "visualizerMode"
> & {
  status?: NowPlayingState["status"];
};

function loadInitialPlayer(): PlayerSnapshot {
  if (typeof window === "undefined") {
    return {
      track: null,
      currentTimeSec: 0,
      durationSec: 0,
      progress: 0,
      volume: 0.82,
      muted: false,
      sourceLabel: undefined,
      explanation: undefined,
      visualizerMode: "bloom",
      status: "idle",
    };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Partial<PlayerSnapshot> : {};
    return {
      track: (parsed.track as TrackListItem | null) ?? null,
      currentTimeSec: Number(parsed.currentTimeSec ?? 0),
      durationSec: Number(parsed.durationSec ?? 0),
      progress: Number(parsed.progress ?? 0),
      volume: Number(parsed.volume ?? 0.82),
      muted: Boolean(parsed.muted),
      sourceLabel: parsed.sourceLabel,
      explanation: parsed.explanation,
      visualizerMode: parsed.visualizerMode ?? "bloom",
      status: parsed.status ?? "idle",
    };
  } catch {
    return {
      track: null,
      currentTimeSec: 0,
      durationSec: 0,
      progress: 0,
      volume: 0.82,
      muted: false,
      sourceLabel: undefined,
      explanation: undefined,
      visualizerMode: "bloom",
      status: "idle",
    };
  }
}

function persistPlayer(snapshot: PlayerSnapshot) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}

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

const initial = loadInitialPlayer();

export const usePlayerStore = create<PlayerStore>((set) => ({
  track: initial.track,
  status: initial.status ?? "idle",
  currentTimeSec: initial.currentTimeSec,
  durationSec: initial.durationSec,
  progress: initial.progress,
  volume: initial.volume,
  muted: initial.muted,
  repeatMode: "off",
  shuffle: false,
  sourceLabel: initial.sourceLabel,
  explanation: initial.explanation,
  visualizerMode: initial.visualizerMode,
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
    set((state) => {
      const status: NowPlayingState["status"] = track ? "loading" : "idle";
      const next = {
        ...state,
        track,
        sourceLabel,
        explanation,
        errorMessage: undefined,
        currentTimeSec: 0,
        durationSec: track?.durationSec ?? 0,
        progress: 0,
        status,
      };
      persistPlayer(next);
      return next;
    }),
  setStatus: (status) =>
    set((state) => {
      const next = { ...state, status };
      persistPlayer(next);
      return next;
    }),
  setError: (errorMessage) =>
    set((state) => {
      const next = { ...state, status: "error" as const, errorMessage };
      persistPlayer(next);
      return next;
    }),
  setTime: (currentTimeSec, durationSec) =>
    set((state) => {
      const next = {
        ...state,
        currentTimeSec,
        durationSec,
        progress: durationSec > 0 ? currentTimeSec / durationSec : 0,
      };
      persistPlayer(next);
      return next;
    }),
  setVolume: (volume) =>
    set((state) => {
      const next = { ...state, volume };
      persistPlayer(next);
      return next;
    }),
  setMuted: (muted) =>
    set((state) => {
      const next = { ...state, muted };
      persistPlayer(next);
      return next;
    }),
  setVisualizerMode: (visualizerMode) =>
    set((state) => {
      const next = { ...state, visualizerMode };
      persistPlayer(next);
      return next;
    }),
  setFrame: (frame) => set({ frame }),
}));
