// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  NOTIFICATION_STORAGE_KEY,
  buildNotificationContent,
  envNotificationsEnabled,
  localPreferenceEnabled,
} from "./useNativeNotifications";

describe("useNativeNotifications helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.unstubAllEnvs();
  });

  it("builds a now-playing notification for track events", () => {
    expect(
      buildNotificationContent({
        event_type: "track_started",
        context: { artist: "Burial", title: "Archangel" },
      }),
    ).toEqual({
      title: "Now Playing",
      body: "Burial - Archangel",
    });
  });

  it("builds a provider degradation notification", () => {
    expect(
      buildNotificationContent({
        event_type: "provider_degraded",
        context: { provider: "MusicBrainz", reason: "timeout" },
      }),
    ).toEqual({
      title: "Provider Degraded",
      body: "MusicBrainz: timeout",
    });
  });

  it("honors localStorage opt-in", () => {
    window.localStorage.setItem(NOTIFICATION_STORAGE_KEY, "true");
    expect(localPreferenceEnabled()).toBe(true);
  });

  it("honors the Vite notification flag", () => {
    vi.stubEnv("VITE_LYRA_NATIVE_NOTIFICATIONS", "true");
    expect(envNotificationsEnabled()).toBe(true);
  });
});
