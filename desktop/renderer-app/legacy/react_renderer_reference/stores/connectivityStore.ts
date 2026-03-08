import { create } from "zustand";
import type { ConnectionState } from "@/services/lyraGateway/types";

interface ApiCallRecord {
  endpoint: string;
  method: string;
  ok: boolean;
  statusCode?: number;
  timestamp: string;
  error?: string;
}

interface ConnectivityStore {
  state: ConnectionState;
  endpoint: string;
  lastError: string | null;
  statusCode: number | null;
  timestamp: string | null;
  lastHealthPayload: Record<string, unknown> | null;
  recentCalls: ApiCallRecord[];
  setLive: (payload?: Record<string, unknown>) => void;
  setDegraded: (error: string, statusCode?: number | null) => void;
  setFixture: (error: string) => void;
  recordCall: (call: ApiCallRecord) => void;
}

export const useConnectivityStore = create<ConnectivityStore>((set) => ({
  state: "DEGRADED",
  endpoint: "",
  lastError: null,
  statusCode: null,
  timestamp: null,
  lastHealthPayload: null,
  recentCalls: [],
  setLive: (payload) =>
    set((state) => ({
      state: "LIVE",
      lastError: null,
      statusCode: 200,
      timestamp: new Date().toISOString(),
      lastHealthPayload: payload ?? state.lastHealthPayload,
    })),
  setDegraded: (error, statusCode = null) =>
    set({
      state: "DEGRADED",
      lastError: error,
      statusCode,
      timestamp: new Date().toISOString(),
    }),
  setFixture: (error) =>
    set({
      state: "FIXTURE",
      lastError: error,
      statusCode: null,
      timestamp: new Date().toISOString(),
    }),
  recordCall: (call) =>
    set((state) => ({
      recentCalls: [call, ...state.recentCalls].slice(0, 8),
      endpoint: call.endpoint,
    })),
}));
