import { browser } from "$app/environment";
import { writable } from "svelte/store";
import { api } from "$lib/tauri";
import type {
  AppShellState,
  BootstrapPayload,
  LegacyImportReport,
  PlaybackState,
  ProviderConfigRecord,
  QueueItemRecord,
  ScanJobRecord,
  TasteProfile
} from "$lib/types";

const defaultShell: AppShellState = {
  libraryOverview: { trackCount: 0, albumCount: 0, artistCount: 0, rootCount: 0 },
  libraryRoots: [],
  playlists: [],
  queue: [],
  playback: {
    status: "idle",
    queueIndex: 0,
    positionSeconds: 0,
    durationSeconds: 0,
    volume: 0.82,
    shuffle: false,
    repeatMode: "off",
    seekSupported: false
  },
  settings: {
    startMinimized: false,
    restoreSession: true,
    queuePanelOpen: true,
    playbackVolumeStep: 5,
    libraryAutoScan: false,
    preferredOutputDevice: null
  },
  providers: [],
  scanJobs: [],
  tasteProfile: {
    dimensions: {},
    confidence: 0,
    totalSignals: 0,
    source: "unknown"
  },
  acquisitionQueuePending: 0
};

export const shell = writable<AppShellState>(defaultShell);
export const bootstrap = writable<BootstrapPayload | null>(null);
export const loading = writable<boolean>(true);
export const errorMessage = writable<string>("");
export const legacyImportReport = writable<LegacyImportReport | null>(null);

export async function loadShell(): Promise<void> {
  if (!browser) return;
  loading.set(true);
  errorMessage.set("");
  try {
    const payload = await api.bootstrap();
    bootstrap.set(payload);
    shell.set(payload.shell);
  } catch (error) {
    errorMessage.set(error instanceof Error ? error.message : "Failed to bootstrap Lyra");
  } finally {
    loading.set(false);
  }
}

export async function refreshShell(): Promise<void> {
  if (!browser) return;
  shell.set(await api.shell());
}

export function registerLyraEvents(): () => void {
  if (!browser) return () => undefined;
  const disposers: Array<() => void> = [];
  const attach = async <T>(event: string, handler: (payload: T) => void) => {
    disposers.push(await api.on<T>(event, handler));
  };
  void attach<PlaybackState>("lyra://playback-updated", (payload) => {
    shell.update((state) => ({ ...state, playback: payload }));
  });
  void attach<QueueItemRecord[]>("lyra://queue-updated", (payload) => {
    shell.update((state) => ({ ...state, queue: payload }));
  });
  void attach<ScanJobRecord>("lyra://scan-progress", (payload) => {
    shell.update((state) => ({
      ...state,
      scanJobs: [payload, ...state.scanJobs.filter((job) => job.id !== payload.id)].slice(0, 20)
    }));
  });
  void attach<ProviderConfigRecord[]>("lyra://provider-updated", (payload) => {
    shell.update((state) => ({ ...state, providers: payload }));
  });
  void attach("lyra://library-updated", async () => {
    await refreshShell();
  });
  void attach("lyra://bootstrap", async () => {
    await refreshShell();
  });
  return () => {
    for (const dispose of disposers) {
      dispose();
    }
  };
}
