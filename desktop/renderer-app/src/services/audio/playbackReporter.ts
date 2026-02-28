export async function reportPlayback(trackId: string, completionRate: number, skipped = false): Promise<void> {
  try {
    await fetch("/api/playback/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
