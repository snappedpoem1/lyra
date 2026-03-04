import { z } from "zod";

export const scoreChipSchema = z.object({
  key: z.string(),
  value: z.number().nullable(),
  label: z.string(),
});

export const trackReasonSchema = z.object({
  type: z.string(),
  text: z.string(),
  score: z.number(),
});

export const trackSchema = z.object({
  trackId: z.string(),
  artist: z.string(),
  title: z.string(),
  path: z.string(),
  album: z.string().optional(),
  year: z.string().optional(),
  durationSec: z.number().optional(),
  versionType: z.string().optional(),
  confidence: z.number().optional(),
  artUrl: z.string().nullable().optional(),
  streamUrl: z.string().optional(),
  reasons: z.array(trackReasonSchema),
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

export const doctorCheckSchema = z.object({
  name: z.string(),
  status: z.enum(["PASS", "WARNING", "FAIL"]),
  details: z.string(),
});

export const doctorSchema = z.array(doctorCheckSchema);

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

export const vibeTrackSchema = z.object({
  path: z.string(),
  artist: z.string(),
  title: z.string(),
  rank: z.number().optional(),
  global_score: z.number().optional(),
  reasons: z.array(trackReasonSchema),
}).passthrough();

export const playlistRunSchema = z.object({
  uuid: z.string(),
  prompt: z.string().optional(),
  created_at: z.string().optional(),
  tracks: z.array(vibeTrackSchema),
}).passthrough();

export const vibeGenerateSchema = z.object({
  meta: z.object({
    prompt: z.string(),
    generated: z.record(z.any()).optional(),
    saved_as: z.string().nullable().optional(),
  }).passthrough(),
  run: playlistRunSchema,
});

export const vibeCreateSchema = z.object({
  prompt: z.string(),
  name: z.string(),
  generated: z.record(z.any()).optional(),
  save: z.record(z.any()),
}).passthrough();

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

export const constellationSchema = z.object({
  nodes: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      inLibrary: z.boolean().optional(),
    }),
  ),
  edges: z.array(
    z.object({
      source: z.string(),
      target: z.string(),
      type: z.string().optional(),
      weight: z.number().optional(),
    }),
  ),
  total_nodes: z.number().optional(),
  total_edges: z.number().optional(),
});

export const tasteProfileSchema = z.object({
  dimensions: z.record(z.number()),
  genre_affinity: z.array(z.object({ genre: z.string(), score: z.number() })).optional(),
  era_distribution: z.record(z.number()).optional(),
  total_signals: z.number().optional(),
  library_stats: z
    .object({
      total_tracks: z.number(),
      scored_tracks: z.number(),
      top_artists: z.array(z.object({ artist: z.string(), count: z.number() })).optional(),
    })
    .optional(),
});

export const artistShrineSchema = z.object({
  artist: z.string(),
  bio: z.string().optional(),
  bio_source: z.string().optional(),
  images: z.record(z.string()).optional(),
  wiki_thumbnail: z.string().optional(),
  formation_year: z.union([z.string(), z.number()]).nullable().optional(),
  origin: z.string().optional(),
  members: z.array(z.string()).optional(),
  scene: z.string().optional(),
  genres: z.array(z.string()).optional(),
  era: z.string().optional(),
  artist_mbid: z.string().optional(),
  lastfm_listeners: z.number().nullable().optional(),
  lastfm_url: z.string().optional(),
  wiki_url: z.string().optional(),
  social_links: z.record(z.string()).optional(),
  related_artists: z.array(
    z.object({ target: z.string(), type: z.string(), weight: z.number() }),
  ).optional(),
  credits: z.array(
    z.object({ role: z.string(), name: z.string(), count: z.number() }),
  ).optional(),
  library_stats: z.object({
    track_count: z.number(),
    album_count: z.number(),
    albums: z.array(z.object({ album: z.string().nullable(), year: z.union([z.string(), z.number()]).nullable() })),
  }).optional(),
});

// ── Oracle Discovery ──────────────────────────────────────────────────────

export const oracleDiscoverySuggestionSchema = z.object({
  artist: z.string(),
  connected_from: z.array(z.string()),
  connection_type: z.string(),
  weight: z.number(),
  score: z.number(),
  reasons: z.array(z.string()),
  already_queued: z.boolean(),
});

export const oracleDiscoverySchema = z.object({
  count: z.number(),
  results: z.array(oracleDiscoverySuggestionSchema),
});

export const oracleGapsSchema = z.object({
  count: z.number(),
  results: z.array(z.object({
    artist: z.string(),
    title: z.string(),
    album: z.string().nullable().optional(),
    popularity: z.number().nullable().optional(),
    release_date: z.string().nullable().optional(),
    spotify_uri: z.string().nullable().optional(),
  })),
});
