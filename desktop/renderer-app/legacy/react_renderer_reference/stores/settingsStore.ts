import { create } from "zustand";
import { DEFAULT_API_BASE, getEnvApiBase, getEnvApiToken, normalizeApiBase } from "@/config/runtime";

const STORAGE_KEY = "lyra-settings";

type SettingsSnapshot = {
  apiBaseUrl: string;
  apiToken: string;
  fixtureMode: boolean;
  developerHud: boolean;
  resumeSession: boolean;
  companionEnabled: boolean;
  companionStyle: "orb" | "pixel";
  notificationsEnabled: boolean;
};

function loadInitial(): SettingsSnapshot {
  if (typeof window === "undefined") {
    return {
      apiBaseUrl: DEFAULT_API_BASE,
      apiToken: "",
      fixtureMode: false,
      developerHud: false,
      resumeSession: true,
      companionEnabled: true,
      companionStyle: "orb",
      notificationsEnabled: false,
    };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Partial<SettingsSnapshot> : {};
    return {
      apiBaseUrl: normalizeApiBase(parsed.apiBaseUrl || getEnvApiBase()),
      apiToken: String(parsed.apiToken || getEnvApiToken()),
      fixtureMode: Boolean(parsed.fixtureMode),
      developerHud: Boolean(parsed.developerHud),
      resumeSession: parsed.resumeSession !== false,
      companionEnabled: parsed.companionEnabled !== false,
      companionStyle: parsed.companionStyle === "pixel" ? "pixel" : "orb",
      notificationsEnabled: Boolean(parsed.notificationsEnabled),
    };
  } catch {
    return {
      apiBaseUrl: getEnvApiBase(),
      apiToken: getEnvApiToken(),
      fixtureMode: false,
      developerHud: false,
      resumeSession: true,
      companionEnabled: true,
      companionStyle: "orb",
      notificationsEnabled: false,
    };
  }
}

function persist(next: SettingsSnapshot) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

interface SettingsStore extends SettingsSnapshot {
  setApiBaseUrl: (value: string) => void;
  setApiToken: (value: string) => void;
  setFixtureMode: (value: boolean) => void;
  setDeveloperHud: (value: boolean) => void;
  setResumeSession: (value: boolean) => void;
  setCompanionEnabled: (value: boolean) => void;
  setCompanionStyle: (value: "orb" | "pixel") => void;
  setNotificationsEnabled: (value: boolean) => void;
}

const initial = loadInitial();

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  ...initial,
  setApiBaseUrl: (value) => {
    const next = { ...get(), apiBaseUrl: normalizeApiBase(value) };
    persist(next);
    set({ apiBaseUrl: next.apiBaseUrl });
  },
  setApiToken: (value) => {
    const next = { ...get(), apiToken: value.trim() };
    persist(next);
    set({ apiToken: next.apiToken });
  },
  setFixtureMode: (value) => {
    const next = { ...get(), fixtureMode: value };
    persist(next);
    set({ fixtureMode: value });
  },
  setDeveloperHud: (value) => {
    const next = { ...get(), developerHud: value };
    persist(next);
    set({ developerHud: value });
  },
  setResumeSession: (value) => {
    const next = { ...get(), resumeSession: value };
    persist(next);
    set({ resumeSession: value });
  },
  setCompanionEnabled: (value) => {
    const next = { ...get(), companionEnabled: value };
    persist(next);
    set({ companionEnabled: value });
  },
  setCompanionStyle: (value) => {
    const next = { ...get(), companionStyle: value };
    persist(next);
    set({ companionStyle: value });
  },
  setNotificationsEnabled: (value) => {
    const next = { ...get(), notificationsEnabled: value };
    persist(next);
    set({ notificationsEnabled: value });
  },
}));
