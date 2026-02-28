import { z } from "zod";

export const scoreChipSchema = z.object({
  key: z.string(),
  value: z.number().nullable(),
  label: z.string(),
});

export const trackSchema = z.object({
  trackId: z.string(),
  artist: z.string(),
  title: z.string(),
  album: z.string().optional(),
  year: z.string().optional(),
  durationSec: z.number().optional(),
  versionType: z.string().optional(),
  confidence: z.number().optional(),
  artUrl: z.string().nullable().optional(),
  streamUrl: z.string(),
  scoreChips: z.array(scoreChipSchema),
  reason: z.string().optional(),
  provenance: z.string().optional(),
  structureHint: z.object({
    bpm: z.number().optional(),
    hasDrop: z.boolean().optional(),
  }).optional(),
});

export const playlistSummarySchema = z.object({
  id: z.string(),
  kind: z.enum(["vibe", "oracle_queue", "ritual", "manual"]),
  title: z.string(),
  subtitle: z.string(),
  narrative: z.string(),
  trackCount: z.number(),
  freshnessLabel: z.string(),
  coverMosaic: z.array(z.string()),
  emotionalSignature: z.array(z.object({ key: z.string(), value: z.number() })),
  lastTouchedLabel: z.string().optional(),
});

export const healthSchema = z.object({
  status: z.string(),
  ok: z.boolean(),
  service: z.string(),
  version: z.string(),
  timestamp: z.number(),
  profile: z.string(),
  write_mode: z.string(),
  db: z.object({ ok: z.boolean() }).passthrough(),
  library: z.object({ ok: z.boolean() }).passthrough(),
  feature_flags: z.record(z.boolean()),
  auth: z.object({ enabled: z.boolean() }),
  cors: z.object({ allowed_origins: z.array(z.string()) }),
  llm: z.record(z.any()),
});

export const vibesSchema = z.object({
  vibes: z.array(z.record(z.any())),
  count: z.number(),
});

export const playlistDetailSchema = z.object({
  id: z.string(),
  kind: z.string(),
  title: z.string(),
  subtitle: z.string(),
  narrative: z.string(),
  trackCount: z.number(),
  freshnessLabel: z.string(),
  coverMosaic: z.array(z.string()),
  emotionalSignature: z.array(z.any()),
  lastTouchedLabel: z.string().optional(),
  query: z.string().optional(),
  tracks: z.array(z.record(z.any())),
  storyBeats: z.array(z.string()),
  arc: z.array(z.object({ step: z.number(), energy: z.number(), valence: z.number(), tension: z.number() })),
  relatedPlaylists: z.array(z.record(z.any())),
  oraclePivots: z.array(z.any()),
});

export const searchSchema = z.object({
  results: z.array(z.record(z.any())),
  count: z.number(),
  original_query: z.string().optional(),
  query: z.string(),
  rewrite: z.record(z.any()).optional(),
});

export const radioResultsSchema = z.object({
  results: z.array(z.record(z.any())),
  count: z.number(),
});

export const queueSchema = z.object({
  queue: z.array(z.record(z.any())),
  count: z.number(),
  mode: z.string(),
});

export const libraryTracksSchema = z.object({
  tracks: z.array(z.record(z.any())),
  count: z.number(),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  query: z.string().optional(),
  artist: z.string().nullable().optional(),
  album: z.string().nullable().optional(),
  artists: z.array(z.object({ name: z.string(), count: z.number() })).optional(),
  albums: z.array(z.object({ name: z.string(), count: z.number() })).optional(),
});

export const libraryArtistsSchema = z.object({
  artists: z.array(z.object({ name: z.string(), count: z.number() })),
  count: z.number(),
  query: z.string().optional(),
});

export const libraryAlbumsSchema = z.object({
  albums: z.array(z.object({ name: z.string(), count: z.number() })),
  count: z.number(),
  query: z.string().optional(),
  artist: z.string().nullable().optional(),
});

export const libraryArtistDetailSchema = z.object({
  artist: z.string(),
  track_count: z.number(),
  album_count: z.number(),
  years: z.array(z.string()),
  albums: z.array(z.object({ name: z.string(), count: z.number() })),
  tracks: z.array(z.record(z.any())),
});

export const libraryAlbumDetailSchema = z.object({
  artist: z.string(),
  album: z.string(),
  track_count: z.number(),
  years: z.array(z.string()),
  tracks: z.array(z.record(z.any())),
});

export const agentSuggestionSchema = z.object({
  suggestion: z.string(),
  action: z.string(),
});

export const dossierSchema = z.object({
  track: z.record(z.any()),
  structure: z.any().optional(),
  lineage: z.array(z.record(z.any())).optional(),
  samples: z.array(z.record(z.any())).optional(),
  fact: z.string().nullable().optional(),
  provenance_notes: z.array(z.string()),
  acquisition_notes: z.array(z.string()),
});
