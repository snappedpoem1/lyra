import { create } from "zustand";
import type { QueueState, TrackListItem } from "@/types/domain";

const STORAGE_KEY = "lyra-queue";

const EMPTY_QUEUE: QueueState = {
  queueId: "empty",
  origin: "silence",
  reorderable: true,
  currentIndex: 0,
  items: [],
};

function loadInitialQueue(): QueueState {
  if (typeof window === "undefined") {
    return EMPTY_QUEUE;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Partial<QueueState> : null;
    if (!parsed || !Array.isArray(parsed.items)) {
      return EMPTY_QUEUE;
    }
    return {
      queueId: parsed.queueId || "persisted",
      origin: parsed.origin || "session",
      algorithm: parsed.algorithm,
      generatedAt: parsed.generatedAt,
      reorderable: parsed.reorderable ?? true,
      currentIndex: Math.max(0, Math.min(Number(parsed.currentIndex ?? 0), Math.max(0, parsed.items.length - 1))),
      items: parsed.items as TrackListItem[],
    };
  } catch {
    return EMPTY_QUEUE;
  }
}

function persistQueue(queue: QueueState) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
}

interface QueueStore {
  queue: QueueState;
  replaceQueue: (queue: QueueState) => void;
  appendTracks: (tracks: TrackListItem[]) => void;
  setCurrentIndex: (index: number) => void;
  setCurrentTrack: (trackId: string) => void;
  moveItem: (from: number, to: number) => void;
  removeItem: (index: number) => void;
  clearQueue: () => void;
}

export const useQueueStore = create<QueueStore>((set) => ({
  queue: loadInitialQueue(),
  replaceQueue: (queue) => {
    persistQueue(queue);
    set({ queue });
  },
  appendTracks: (tracks) =>
    set((state) => {
      const queue = {
        ...state.queue,
        items: [...state.queue.items, ...tracks],
      };
      persistQueue(queue);
      return { queue };
    }),
  setCurrentIndex: (index) =>
    set((state) => {
      const queue = {
        ...state.queue,
        currentIndex: Math.max(0, Math.min(index, Math.max(0, state.queue.items.length - 1))),
      };
      persistQueue(queue);
      return { queue };
    }),
  setCurrentTrack: (trackId) =>
    set((state) => {
      const queue = {
        ...state.queue,
        currentIndex: Math.max(0, state.queue.items.findIndex((item) => item.trackId === trackId)),
      };
      persistQueue(queue);
      return { queue };
    }),
  moveItem: (from, to) =>
    set((state) => {
      const items = [...state.queue.items];
      if (from < 0 || from >= items.length || to < 0 || to >= items.length || from === to) {
        return state;
      }
      const [moved] = items.splice(from, 1);
      items.splice(to, 0, moved);
      const queue = {
        ...state.queue,
        items,
      };
      persistQueue(queue);
      return { queue };
    }),
  removeItem: (index) =>
    set((state) => {
      if (index < 0 || index >= state.queue.items.length) {
        return state;
      }
      const items = state.queue.items.filter((_, itemIndex) => itemIndex !== index);
      const currentIndex = items.length
        ? Math.max(0, Math.min(state.queue.currentIndex > index ? state.queue.currentIndex - 1 : state.queue.currentIndex, items.length - 1))
        : 0;
      const queue = {
        ...state.queue,
        items,
        currentIndex,
      };
      persistQueue(queue);
      return { queue };
    }),
  clearQueue: () => {
    const queue = { ...EMPTY_QUEUE, origin: "manual" };
    persistQueue(queue);
    set({ queue });
  },
}));
