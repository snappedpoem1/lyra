import { create } from "zustand";

interface SearchStore {
  query: string;
  rewrittenQuery: string;
  setQuery: (query: string) => void;
  setRewrittenQuery: (query: string) => void;
}

export const useSearchStore = create<SearchStore>((set) => ({
  query: "cathedral bass with analog ache and haunted warmth",
  rewrittenQuery: "",
  setQuery: (query) => set({ query }),
  setRewrittenQuery: (rewrittenQuery) => set({ rewrittenQuery }),
}));
