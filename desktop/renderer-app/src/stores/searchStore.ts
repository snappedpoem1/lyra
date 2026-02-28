import { create } from "zustand";

interface SearchStore {
  query: string;
  rewrittenQuery: string;
  setQuery: (query: string) => void;
  setRewrittenQuery: (query: string) => void;
}

export const useSearchStore = create<SearchStore>((set) => ({
  query: "",
  rewrittenQuery: "",
  setQuery: (query) => set({ query }),
  setRewrittenQuery: (rewrittenQuery) => set({ rewrittenQuery }),
}));
