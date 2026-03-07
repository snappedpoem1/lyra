# SPEC-007 — Ingest Confidence and Normalization Lifecycle

Version: 1.0 — March 7, 2026

## 1) Problem

The current ingest pipeline is opaque. A track either appears in the library or it doesn't.
When something goes wrong — a mismatched file, a failed guard check, a missing embedding — there is no way to tell where the pipeline stalled or what the trust level of a successfully ingested track actually is.

Duplicate and mismatch handling is currently implicit in queue-reconciliation logic.
There is no user-visible signal for "this track was acquired but not yet validated" vs
"this track is fully placed and trusted."

## 2) Goals

1. Make acquisition trust a visible, queryable lifecycle rather than hidden plumbing.
2. Give diagnostics and status surfaces a first-class trust signal per track.
3. Keep the lifecycle append-only so historical pipeline state is never lost.
4. Make failures and partial states visible with explicit reason codes.

## 3) Non-Goals

- This spec does not replace the `acquisition_queue` table or its status field.
- This spec does not require AcoustID or beets integration (those are enrichment steps that can write evidence into the same table later).
- No UI surfaces are required by this spec — diagnostics and API are sufficient for Wave 8.

## 4) Lifecycle States

```
acquired → validated → normalized → enriched → placed
                ↓           ↓           ↓
            rejected    rejected    rejected
```

| State | Meaning |
|---|---|
| `acquired` | File arrived in staging/downloads. Guard check has not yet run. |
| `validated` | Guard check passed — not junk, not a label, not a duplicate of an existing active track. |
| `normalized` | Filename and tag normalization applied (via `name_cleaner`). File moved to library folder. |
| `enriched` | At least one external enrichment source confirmed the identity (MBID, AcoustID, Discogs, or in-library similarity). |
| `placed` | Track scanned into `tracks` table, embedding indexed, scored. Fully trusted and queryable. |
| `rejected` | Guard or validation check failed. Not added to library. Reason code is recorded. |

A track must progress through states in order. Skipping states is allowed only for tracks that were already in the library before this spec was introduced (backfill rows are written with `placed` and `reason_codes: ["backfill"]`).

## 5) Reason Codes

Reason codes are short strings recorded at each transition. Multiple codes per transition are allowed.

### Validation reason codes

| Code | Meaning |
|---|---|
| `guard_pass` | Guard check passed all criteria |
| `guard_junk` | Rejected by junk pattern match |
| `guard_label` | Rejected because artist is a known record label |
| `guard_duplicate` | Rejected because an active track with matching artist+title already exists |
| `guard_format_unsupported` | Rejected because file format is not supported |
| `guard_size_too_small` | Rejected because file is suspiciously small (< 1 MB) |

### Normalization reason codes

| Code | Meaning |
|---|---|
| `normalized_name` | Filename cleaned and standardized |
| `normalized_tags` | ID3/Vorbis tags aligned with normalized filename |
| `moved_to_library` | File physically moved to library root |

### Enrichment reason codes

| Code | Meaning |
|---|---|
| `mbid_confirmed` | MusicBrainz recording MBID confirmed |
| `acoustid_confirmed` | AcoustID fingerprint matched |
| `discogs_confirmed` | Discogs release match found |
| `local_similarity_confirmed` | High-similarity match found within existing library (cosine ≥ 0.92) |
| `enrichment_skipped` | No enrichment source available; track placed without external confirmation |

### Placement reason codes

| Code | Meaning |
|---|---|
| `scan_complete` | Track scanned into `tracks` table |
| `embedding_indexed` | CLAP embedding written to ChromaDB |
| `scored` | 10-dimensional score written to `track_scores` |

## 6) Database Contract

### New table: `ingest_confidence`

```sql
CREATE TABLE IF NOT EXISTS ingest_confidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT,
    filepath TEXT NOT NULL,
    state TEXT NOT NULL,
    reason_codes TEXT NOT NULL DEFAULT '[]',  -- JSON array of strings
    source TEXT,                               -- originating queue row artist+title or filepath
    transitioned_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
)
```

- One row per state transition. A track that completes the full pipeline has 5 rows (`acquired` → `validated` → `normalized` → `enriched` → `placed`).
- A rejected track has 2 rows: `acquired` + `rejected`.
- `track_id` is NULL for `acquired` and `validated` rows (the DB row does not yet exist).
- `filepath` is the canonical path at the time of the transition (may differ between `acquired` and `placed` if normalization moved the file).
- `reason_codes` is a JSON array of strings drawn from the codes in Section 5.

### Current state query

```sql
SELECT filepath, state, reason_codes, transitioned_at
FROM ingest_confidence
WHERE filepath = ?
ORDER BY transitioned_at DESC
LIMIT 1
```

### Trust summary query (for diagnostics)

```sql
SELECT state, COUNT(*) as count
FROM ingest_confidence ic
WHERE ic.id = (
    SELECT MAX(id) FROM ingest_confidence WHERE filepath = ic.filepath
)
GROUP BY state
```

## 7) API Contract

### `GET /api/ingest/confidence/summary`

Returns aggregate counts by state for the most-recent transition per unique filepath.

```json
{
  "summary": {
    "acquired": 0,
    "validated": 0,
    "normalized": 0,
    "enriched": 0,
    "placed": 2454,
    "rejected": 12
  },
  "total_unique_filepaths": 2466,
  "backfill_count": 2454
}
```

### `GET /api/ingest/confidence/recent?limit=20`

Returns the most-recent N transitions across all tracks, newest first.

```json
{
  "transitions": [
    {
      "filepath": "...",
      "track_id": "abc123",
      "state": "placed",
      "reason_codes": ["scan_complete", "embedding_indexed", "scored"],
      "transitioned_at": 1741385400.0
    }
  ]
}
```

## 8) Doctor Surface

`oracle doctor` will add a single summary line:

```
Ingest Confidence  PASS   2454 placed / 12 rejected / 0 stalled
```

A "stalled" track is one whose most-recent state is `acquired`, `validated`, or `normalized` and whose last transition is more than 30 minutes ago.

## 9) Implementation Modules

- `oracle/ingest_confidence.py` — state machine and DB helpers
- `oracle/db/schema.py` — `ingest_confidence` table added to `_apply_schema()`
- `oracle/ingest_watcher.py` — calls `record_transition()` at each pipeline stage
- `oracle/doctor.py` — calls `get_confidence_summary()` for the new check
- `oracle/api/blueprints/ingest.py` — new blueprint for the two endpoints above
- `oracle/api/__init__.py` — register the new blueprint

## 10) Backfill Rule

On first run after schema migration, `oracle/ingest_confidence.py` will write one
`placed` row with `reason_codes: ["backfill"]` for every track in `tracks` that has no
existing `ingest_confidence` row. This ensures diagnostics immediately show a meaningful
placed count rather than zero.
