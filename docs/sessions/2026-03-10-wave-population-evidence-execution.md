# Session S-20260310-11 — WAVE: Population + Universal Evidence + Execution Confidence

**Date:** March 10, 2026
**Session ID:** S-20260310-11

---

## Goal

Execute the WAVE: POPULATION + UNIVERSAL EVIDENCE + EXECUTION CONFIDENCE work.
Five objectives stated at session open:

1. Library-wide lineage population — make the MB ingestor runnable against the actual library with Tauri command exposure, progress visibility, and resumability.
2. Library-wide audio evidence population — expose batch extraction as Tauri commands with progress/status tracking.
3. Explainability universality — new tests proving audio_proof evidence surfaces in explain_track after extraction.
4. Native acquisition execution proof — integration test proving honest lifecycle state transitions.
5. Packaged/runtime confidence — materially improve coverage in backend_runtime_confidence.rs.

User directive: **Do the work. Do not give me a plan-only answer.**

---

## What Changed

### `crates/lyra-core/src/artist_intelligence.rs`

- `IngestResult` struct now derives `Serialize + Deserialize` with `camelCase` serde — required to return from a Tauri command.
- `LineageIngestStatus` struct added: `pending_artists`, `last_run_at`, `last_run_artists_processed`, `last_run_edges_inserted`, `last_run_errors`, `total_verified_edges`.
- `log_ingest_run(conn, result)` — inserts a row into `lineage_ingest_log` after each run.
- `ingest_status(conn)` — returns `LineageIngestStatus` with pending count + last run summary.
- `ingest_artist_relationships` updated to call `log_ingest_run` before returning.

### `crates/lyra-core/src/track_audio_features.rs`

- `BatchExtractResult` struct now derives `Serialize + Deserialize` with `camelCase` serde.
- `AudioExtractionStatus` struct added: `pending_tracks`, `last_run_at`, `last_run_processed`, `last_run_succeeded`, `last_run_failed`, `total_with_features`.
- `log_extraction_run(conn, result)` — inserts a row into `audio_extraction_log` after each run.
- `extraction_status(conn)` — returns `AudioExtractionStatus` with pending count + last run summary.
- `batch_extract` updated to call `log_extraction_run` before returning.

### `crates/lyra-core/src/db.rs`

Added two new tables to the schema (in `init_database`):

```sql
CREATE TABLE IF NOT EXISTS lineage_ingest_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at TEXT NOT NULL,
  artists_processed INTEGER NOT NULL DEFAULT 0,
  edges_inserted INTEGER NOT NULL DEFAULT 0,
  artists_skipped INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lineage_ingest_log_run_at ON lineage_ingest_log(run_at DESC);
CREATE TABLE IF NOT EXISTS audio_extraction_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at TEXT NOT NULL,
  tracks_processed INTEGER NOT NULL DEFAULT 0,
  tracks_succeeded INTEGER NOT NULL DEFAULT 0,
  tracks_failed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audio_extraction_log_run_at ON audio_extraction_log(run_at DESC);
```

### `crates/lyra-core/src/lib.rs`

Two new LyraCore methods added:

```rust
pub fn get_lineage_ingest_status(&self) -> artist_intelligence::LineageIngestStatus
pub fn get_audio_extraction_status(&self) -> track_audio_features::AudioExtractionStatus
```

### `desktop/renderer-app/src-tauri/src/main.rs`

Imports added:

```rust
use lyra_core::artist_intelligence::{IngestResult, LineageIngestStatus};
use lyra_core::track_audio_features::{AudioExtractionStatus, BatchExtractResult};
```

Six new Tauri commands added and registered in `invoke_handler`:

- `ingest_artist_relationships(limit: Option<usize>)` → `Result<IngestResult, String>`
- `pending_artist_ingestion_count()` → `usize`
- `get_lineage_ingest_status()` → `LineageIngestStatus`
- `extract_audio_features_batch(limit: Option<usize>, force: Option<bool>)` → `BatchExtractResult`
- `pending_audio_extraction_count()` → `i64`
- `get_audio_extraction_status()` → `AudioExtractionStatus`

### `crates/lyra-core/src/oracle.rs` — new tests

- `audio_features_extracted_appear_in_explain_track_as_audio_proof_evidence`: seeds a track with features via `upsert_features`, calls `explain_track`, asserts evidence items with `category == "audio_proof"` and tag/PCM anchors appear.
- `verified_lineage_edges_from_ingest_appear_in_related_artists_surface`: inserts a `artist_lineage_edges` row with `evidence_level = 'verified'`, calls `get_related_artists`, asserts the edge surfaces with correct evidence level.

### `crates/lyra-core/tests/backend_runtime_confidence.rs` — four new tests

1. `lineage_ingest_run_with_cached_mb_edges_persists_and_is_queryable`: seeds MB cache with MBID + relations, calls `ingest_artist_relationships`, asserts `edges_inserted > 0` and `ingest_status` shows `last_run_at`.
2. `audio_extraction_status_reports_after_batch_run`: calls `batch_extract` on empty library, asserts `extraction_status.last_run_at` is populated after the run.
3. `acquisition_lifecycle_transitions_are_honest`: queues a track, transitions through validated → failed, asserts `failure_stage`, `failure_reason`, `failed_at` are all correct.
4. `repeated_bootstrap_cycles_are_stable`: creates/drops LyraCore 3 times from the same root path, asserts each cycle starts clean and finds the same library state.

---

## Test Results

```
test result: ok. 75 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

`cargo check -p lyra-core`: EXIT:0
`cargo check` (src-tauri): EXIT:0

---

## BA Matrix Movement

| ID | Before | After | Evidence |
|----|--------|-------|----------|
| BA-10 | Partial | **Pass** | Lineage pipeline exposed as Tauri commands; `lineage_ingest_log` table; 2 new tests prove edge persistence and route surface appearance |
| BA-13 | Partial | **Pass** | Audio extraction exposed as Tauri commands; `audio_extraction_log` table; oracle test proves `audio_proof` evidence in explain_track |
| BA-11 | Partial | Partial | Strengthened evidence note (audio_proof now proven); universality still incomplete |
| BA-14 | Partial | Partial | 3-cycle bootstrap soak + lifecycle test added; clean-machine packaged proof still missing |

Summary: Pass count 10 → 12; Partial count 4 → 2.

---

## Next

- Run `ingest_artist_relationships` against the real library (via Tauri frontend or future CLI hook).
- Run `extract_audio_features_batch` across the real library to populate features for actual files.
- Advance BA-11 universality (carry audio_proof into composer/route explanation surfaces).
- Advance BA-14 toward clean-machine packaged soak.
