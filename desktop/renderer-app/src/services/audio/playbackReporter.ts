import { resolveApiUrl } from "@/services/lyraGateway/client";
import { useSettingsStore } from "@/stores/settingsStore";

export async function reportPlayback(trackId: string, completionRate: number, skipped = false): Promise<void> {
  try {
    const headers: HeadersInit = { "Content-Type": "application/json" };
    const token = useSettingsStore.getState().apiToken;
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    await fetch(resolveApiUrl("/api/playback/record"), {
      method: "POST",
      headers,
      body: JSON.stringify({
        track_id: trackId,
        context: "lyra-renderer",
        completion_rate: completionRate,
        skipped,
      }),
    });
  } catch {
    // Keep listening even if telemetry misses a beat.
  }
}
