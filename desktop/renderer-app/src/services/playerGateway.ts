import { z } from "zod";
import { resolveApiUrl, requestJson } from "@/services/lyraGateway/client";
import type { TrackListItem } from "@/types/domain";

const playerTrackSchema = z.object({
  track_id: z.string(),
  artist: z.string(),
  title: z.string(),
  album: z.string(),
  duration_ms: z.number().int().nonnegative(),
  filepath: z.string(),
});

const playerStateSchema = z.object({
  status: z.string(),
  current_track: playerTrackSchema.nullable(),
  position_ms: z.number().int().nonnegative(),
  duration_ms: z.number().int().nonnegative(),
  volume: z.number(),
  muted: z.boolean(),
  shuffle: z.boolean(),
  repeat_mode: z.enum(["off", "one", "all"]),
  updated_at: z.number(),
  current_queue_index: z.number().int().nonnegative(),
});

const playerQueueSchema = z.object({
  items: z.array(playerTrackSchema),
  current_index: z.number().int().nonnegative(),
  count: z.number().int().nonnegative(),
});

const playerEventSchema = z.object({
  type: z.string(),
  ts: z.number().nullable().optional(),
  state: playerStateSchema.optional(),
  queue: playerQueueSchema.optional(),
  track: playerTrackSchema.nullable().optional(),
  error: z.object({ message: z.string() }).optional(),
});

export type PlayerStatePayload = z.infer<typeof playerStateSchema>;
export type PlayerQueuePayload = z.infer<typeof playerQueueSchema>;
export type PlayerEventPayload = z.infer<typeof playerEventSchema>;

function toTrackListItem(track: z.infer<typeof playerTrackSchema>): TrackListItem {
  return {
    trackId: track.track_id,
    artist: track.artist,
    title: track.title,
    album: track.album || undefined,
    durationSec: track.duration_ms > 0 ? track.duration_ms / 1000 : undefined,
    path: track.filepath || "",
    streamUrl: track.track_id ? `/api/stream/${track.track_id}` : undefined,
    reasons: [],
    scoreChips: [],
  };
}

export function mapPlayerTrack(track: z.infer<typeof playerTrackSchema> | null): TrackListItem | null {
  if (!track) {
    return null;
  }
  return toTrackListItem(track);
}

export function mapPlayerQueueItems(payload: PlayerQueuePayload): TrackListItem[] {
  return payload.items.map((item) => toTrackListItem(item));
}

async function playerPost<T>(
  path: string,
  schema: z.ZodType<T>,
  body?: Record<string, unknown>,
): Promise<T> {
  return requestJson(path, schema, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

export async function getPlayerState(): Promise<PlayerStatePayload> {
  return requestJson("/api/player/state", playerStateSchema, undefined, 6000, 0);
}

export async function getPlayerQueue(): Promise<PlayerQueuePayload> {
  return requestJson("/api/player/queue", playerQueueSchema, undefined, 6000, 0);
}

export async function playerPlay(payload?: { track_id?: string; queue_index?: number }): Promise<PlayerStatePayload> {
  return playerPost("/api/player/play", playerStateSchema, payload);
}

export async function playerPause(): Promise<PlayerStatePayload> {
  return playerPost("/api/player/pause", playerStateSchema);
}

export async function playerSeek(positionMs: number): Promise<PlayerStatePayload> {
  return playerPost("/api/player/seek", playerStateSchema, { position_ms: positionMs });
}

export async function playerNext(): Promise<PlayerStatePayload> {
  return playerPost("/api/player/next", playerStateSchema);
}

export async function playerPrevious(): Promise<PlayerStatePayload> {
  return playerPost("/api/player/previous", playerStateSchema);
}

export async function playerQueueAdd(trackId: string, atIndex?: number): Promise<PlayerQueuePayload> {
  const payload: Record<string, unknown> = { track_id: trackId };
  if (typeof atIndex === "number") {
    payload["at_index"] = atIndex;
  }
  return playerPost("/api/player/queue/add", playerQueueSchema, payload);
}

export async function playerQueueReorder(orderedTrackIds: string[]): Promise<PlayerQueuePayload> {
  return playerPost("/api/player/queue/reorder", playerQueueSchema, {
    ordered_track_ids: orderedTrackIds,
  });
}

export async function playerSetMode(payload: { shuffle?: boolean; repeat_mode?: "off" | "one" | "all" }): Promise<PlayerStatePayload> {
  return playerPost("/api/player/mode", playerStateSchema, payload);
}

export function listenPlayerEvents(
  onEvent: (event: PlayerEventPayload) => void,
  onError: (message: string) => void,
): () => void {
  if (typeof window === "undefined" || typeof window.EventSource === "undefined") {
    return () => undefined;
  }
  const source = new window.EventSource(resolveApiUrl("/ws/player"));

  source.onmessage = (event) => {
    try {
      const raw = JSON.parse(event.data) as unknown;
      const payload = playerEventSchema.parse(raw);
      onEvent(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to parse player event";
      onError(message);
    }
  };

  source.onerror = () => {
    onError("Player event stream disconnected");
  };

  return () => {
    source.close();
  };
}
