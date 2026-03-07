import { useEffect, useRef } from "react";
import { resolveApiUrl } from "@/services/lyraGateway/client";
import { useSettingsStore } from "@/stores/settingsStore";

export interface NativeNotificationEvent {
  event_type: string;
  context: Record<string, string>;
  at?: number;
}

type NotificationContent = {
  title: string;
  body: string;
};

const NOTIFICATION_STORAGE_KEY = "lyra:nativeNotifications";
const SUPPORTED_EVENT_TYPES = new Set<string>([
  "track_changed",
  "track_started",
  "acquisition_complete",
  "acquisition_queued",
  "provider_degraded",
]);

function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    ("__TAURI_IPC__" in window || "__TAURI_INTERNALS__" in window)
  );
}

function envNotificationsEnabled(): boolean {
  return String(import.meta.env.VITE_LYRA_NATIVE_NOTIFICATIONS ?? "").trim().toLowerCase() === "true";
}

function localPreferenceEnabled(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(NOTIFICATION_STORAGE_KEY) === "true";
}

function eventFingerprint(event: NativeNotificationEvent): string {
  return JSON.stringify({
    event_type: event.event_type,
    context: event.context,
    at: event.at ?? 0,
  });
}

function buildNotificationContent(event: NativeNotificationEvent): NotificationContent | null {
  const artist = event.context.artist?.trim() ?? "";
  const title = event.context.title?.trim() ?? "";
  const provider = event.context.provider?.trim() ?? "";
  const reason = event.context.reason?.trim() ?? "";

  switch (event.event_type) {
    case "track_changed":
    case "track_started":
      if (!artist && !title) {
        return null;
      }
      return {
        title: "Now Playing",
        body: [artist, title].filter(Boolean).join(" - "),
      };
    case "acquisition_complete":
    case "acquisition_queued":
      if (!artist && !title) {
        return null;
      }
      return {
        title: "Acquisition Update",
        body: [artist, title].filter(Boolean).join(" - "),
      };
    case "provider_degraded":
      if (!provider) {
        return null;
      }
      return {
        title: "Provider Degraded",
        body: reason ? `${provider}: ${reason}` : `${provider} is unavailable right now.`,
      };
    default:
      return null;
  }
}

async function windowIsFocused(): Promise<boolean> {
  if (typeof document !== "undefined" && document.hasFocus()) {
    return true;
  }

  if (!isTauriRuntime()) {
    return false;
  }

  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    return await getCurrentWindow().isFocused();
  } catch {
    return typeof document !== "undefined" ? document.hasFocus() : false;
  }
}

async function sendNativeNotification(event: NativeNotificationEvent): Promise<void> {
  const content = buildNotificationContent(event);
  if (!content) {
    return;
  }

  const { isPermissionGranted, requestPermission, sendNotification } = await import("@tauri-apps/plugin-notification");
  let granted = await isPermissionGranted();
  if (!granted) {
    granted = (await requestPermission()) === "granted";
  }
  if (!granted) {
    return;
  }

  await sendNotification(content);
}

export function useNativeNotifications(): void {
  const notificationsEnabled = useSettingsStore((state) => state.notificationsEnabled);
  const lastFingerprintRef = useRef<string>("");

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.EventSource === "undefined") {
      return;
    }
    if (!isTauriRuntime()) {
      return;
    }
    if (!(notificationsEnabled || envNotificationsEnabled() || localPreferenceEnabled())) {
      return;
    }

    let active = true;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let source: EventSource | null = null;

    const connect = () => {
      if (!active) {
        return;
      }

      source = new window.EventSource(resolveApiUrl("/ws/companion"));
      source.onmessage = (message) => {
        if (!active) {
          return;
        }

        try {
          const event = JSON.parse(message.data) as NativeNotificationEvent;
          if (!SUPPORTED_EVENT_TYPES.has(event.event_type)) {
            return;
          }

          const fingerprint = eventFingerprint(event);
          if (fingerprint === lastFingerprintRef.current) {
            return;
          }

          void windowIsFocused().then((focused) => {
            if (!focused) {
              lastFingerprintRef.current = fingerprint;
              void sendNativeNotification(event);
            }
          });
        } catch {
          return;
        }
      };

      source.onerror = () => {
        source?.close();
        source = null;
        if (active) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    return () => {
      active = false;
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
      }
      source?.close();
    };
  }, [notificationsEnabled]);
}

export {
  NOTIFICATION_STORAGE_KEY,
  buildNotificationContent,
  envNotificationsEnabled,
  localPreferenceEnabled,
};
