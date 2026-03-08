export interface HostTransportPayload {
  action: "play-pause" | "next" | "previous" | string;
}

export interface HostBootPayload {
  phase: string;
  message: string;
  ready: boolean;
}

/**
 * Detect whether the app is running inside a Tauri host.
 * Guards against both Tauri v1 (__TAURI_IPC__) and Tauri v2 (__TAURI_INTERNALS__).
 */
function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    ("__TAURI_IPC__" in window || "__TAURI_INTERNALS__" in window)
  );
}

export async function getHostBackendBaseUrl(): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const baseUrl = await invoke<string>("get_backend_base_url");
    const trimmed = baseUrl.trim();
    return trimmed.length > 0 ? trimmed.replace(/\/+$/, "") : null;
  } catch {
    return null;
  }
}

export async function listenHostTransport(
  handler: (payload: HostTransportPayload) => void,
): Promise<() => void> {
  // Deprecated bridge: tray/media controls now dispatch directly to backend
  // player commands inside the host process.
  void handler;
  return () => {
    return undefined;
  };
}

export async function listenHostBootStatus(
  handler: (payload: HostBootPayload) => void,
): Promise<() => void> {
  if (!isTauriRuntime()) {
    return () => undefined;
  }

  const { listen } = await import("@tauri-apps/api/event");
  const unlisten = await listen<HostBootPayload>("lyra://boot-status", (event) => {
    handler(event.payload);
  });

  return () => {
    unlisten();
  };
}
