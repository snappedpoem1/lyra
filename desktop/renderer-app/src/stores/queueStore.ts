import { create } from "zustand";
import type { QueueState, TrackListItem } from "@/types/domain";

interface QueueStore {
  queue: QueueState;
  replaceQueue: (queue: QueueState) => void;
  appendTracks: (tracks: TrackListItem[]) => void;
  setCurrentIndex: (index: number) => void;
  setCurrentTrack: (trackId: string) => void;
  moveItem: (from: number, to: number) => void;
}

export const useQueueStore = create<QueueStore>((set) => ({
  queue: {
    queueId: "empty",
    origin: "silence",
    reorderable: true,
    currentIndex: 0,
    items: [],
  },
  replaceQueue: (queue) => set({ queue }),
  appendTracks: (tracks) =>
    set((state) => ({
      queue: {
        ...state.queue,
        items: [...state.queue.items, ...tracks],
      },
    })),
  setCurrentIndex: (index) =>
    set((state) => ({
      queue: {
        ...state.queue,
        currentIndex: Math.max(0, Math.min(index, Math.max(0, state.queue.items.length - 1))),
      },
    })),
  setCurrentTrack: (trackId) =>
    set((state) => ({
      queue: {
        ...state.queue,
        currentIndex: Math.max(0, state.queue.items.findIndex((item) => item.trackId === trackId)),
      },
    })),
  moveItem: (from, to) =>
    set((state) => {
      const items = [...state.queue.items];
      const [moved] = items.splice(from, 1);
      items.splice(to, 0, moved);
      return {
        queue: {
          ...state.queue,
          items,
        },
      };
    }),
}));
