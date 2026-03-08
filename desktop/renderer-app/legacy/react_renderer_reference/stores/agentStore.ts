import { create } from "zustand";
import type { AgentResponse } from "@/types/domain";

interface AgentMessage {
  role: "user" | "lyra";
  text: string;
  thought?: string;
  action?: string;
  timestamp: string;
}

interface AgentStore {
  messages: AgentMessage[];
  loading: boolean;
  lastSuggestion: string | null;
  lastFactDrop: string | null;
  factDropTrackId: string | null;
  addUserMessage: (text: string) => void;
  addAgentResponse: (response: AgentResponse) => void;
  setLoading: (loading: boolean) => void;
  setSuggestion: (suggestion: string | null) => void;
  setFactDrop: (trackId: string | null, fact: string | null) => void;
  clearMessages: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  messages: [],
  loading: false,
  lastSuggestion: null,
  lastFactDrop: null,
  factDropTrackId: null,

  addUserMessage: (text) =>
    set({
      messages: [...get().messages, { role: "user", text, timestamp: new Date().toISOString() }],
    }),

  addAgentResponse: (response) =>
    set({
      messages: [
        ...get().messages,
        {
          role: "lyra",
          text: response.response ?? response.thought ?? "...",
          thought: response.thought,
          action: response.action || undefined,
          timestamp: new Date().toISOString(),
        },
      ],
      loading: false,
    }),

  setLoading: (loading) => set({ loading }),

  setSuggestion: (suggestion) => set({ lastSuggestion: suggestion }),

  setFactDrop: (trackId, fact) => set({ factDropTrackId: trackId, lastFactDrop: fact }),

  clearMessages: () => set({ messages: [] }),
}));
