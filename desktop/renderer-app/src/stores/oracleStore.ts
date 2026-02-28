import { create } from "zustand";
import type { OracleMode } from "@/types/domain";

interface OracleStore {
  mode: OracleMode;
  setMode: (mode: OracleMode) => void;
}

export const useOracleStore = create<OracleStore>((set) => ({
  mode: "flow",
  setMode: (mode) => set({ mode }),
}));
