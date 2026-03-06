export interface HostTransportPayload {
  action: "play-pause" | "next" | "previous" | string;
}

export interface HostBootPayload {
  phase: string;
  message: string;
  ready: boolean;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_IPC__" in window;
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
