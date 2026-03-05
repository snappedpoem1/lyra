# Session: Codebase Integrity Pass

**Session ID:** S-20260305-02  
**Date:** 2026-03-05  
**Goal:** Audit and fix crashes, connection leaks, broken acquisition fallbacks, config path divergence, and performance bottlenecks across the entire codebase.

---

## Context

An automated audit identified 43 findings across 7 areas. This session implemented all fixes across 5 milestones.

---

## Milestone 0 — Critical Crash Fixes

| Fix | File | Problem | Resolution |
|---|---|---|---|
| `AcquisitionWaterfall` ImportError | `oracle/worker.py` | `job_acquire_drain()` tried to import non-existent `AcquisitionWaterfall` class — acquisition drain crashed every 10 min | Changed to `from oracle.acquirers.waterfall import acquire as waterfall_acquire` |
| `guard._check_duplicate()` wrong DB | `oracle/acquirers/guard.py` | Used `sqlite3.connect("lyra_registry.db")` (relative path) — opened wrong DB unless CWD was repo root; all dup checks silently passed | Replaced with `get_connection()` + `try/finally` |
| T3 slskd premature success | `oracle/acquirers/waterfall.py` | Returned `success=True` on "queued" status before file existed — queue items marked done prematurely | Changed to `success=False, error="slskd queued but file not yet materialised"` |

---

## Milestone 1 — Connection Hygiene

All call sites that opened connections without guaranteed close fixed with `try/finally`:

- `oracle/radio.py` — `get_discovery_track`, `get_taste_profile`, `_random_tracks`, `get_lastfm_discovery`
- `oracle/radio.py _store_queue()` — converted DELETE+INSERT to atomic `BEGIN`/`ROLLBACK`/`executemany` transaction
- `oracle/vibes.py save_playlist_run()` — replaced raw `sqlite3.connect(str(DB_PATH))` with `get_connection()`
- `oracle/ingest_watcher.py _reconcile_downloaded_queue_rows()` — moved `conn` outside retry loop; single `finally`
- `oracle/acquirers/waterfall.py _log_acquisition()` — added `try/finally`
- `oracle/api/blueprints/acquire.py` — `api_acquire_queue`, `api_spotify_missing`, `api_spotify_stats` all wrapped; `_BATCH_JOB_TTL` eviction added to `_batch_jobs` dict
- `oracle/acquirers/smart_pipeline.py SmartAcquisition` — added `__enter__`/`__exit__` context manager

---

## Milestone 2 — Acquisition Pipeline Correctness

| Fix | File |
|---|---|
| Removed hardcoded `DOWNLOAD_DIR` constant → lazy `_get_download_dir()` from `oracle.config` | `realdebrid.py`, `spotdl.py` |
| Removed hardcoded `PROJECT_ROOT / download_dir` → lazy config | `ytdlp.py` |
| `add_torrent_file()` now uses `_request("PUT", ...)` for retry coverage | `realdebrid.py` |
| Removed dead `check_instant_availability()` HTTP call (deprecated endpoint, always False) | `realdebrid.py` |
| `asyncio.run()` in T3 replaced with safe wrapper via `get_running_loop()` / `ThreadPoolExecutor` fallback | `waterfall.py` |
| Converted module-level `os.getenv()` globals to `_get_qobuz_config()` lazy function | `qobuz.py` |
| Created T2 stub so waterfall import no longer raises `ImportError` | `oracle/acquirers/streamrip.py` (new) |
| APScheduler `max_workers` 2 → 5 | `worker.py` |

---

## Milestone 3 — Batch & Performance Refactors

| Fix | File | Impact |
|---|---|---|
| `score_all()` now batch-fetches embeddings (1 ChromaDB call vs N), pre-fetches already-scored IDs (1 SQL vs N), and persists via `executemany` | `oracle/scorer.py` | For 2,454 tracks: ~2,454 Chroma calls → 1; ~2,454 INSERT calls → 1 batch |
| `get_chaos_track()` replaced O(n) Python cosine loop with ChromaDB ANN query using negated vector | `oracle/radio.py` | No longer loads all embeddings into Python; O(1) index call instead |
| Normalizer apply loop replaced with `cursor.executemany()` | `oracle/normalizer.py` | Single transaction for all normalization changes |

---

## Test Results

```
python -m pytest -q
64 passed in 8.51s
```

No regressions.

---

## What Was Deferred

- **M4 — Title normalization consolidation (G-033):** Three implementations (`guard._clean_title`, `scanner._deep_clean_title`, `name_cleaner.clean_title`) diverge in pattern coverage. Consolidation needs behavior-verified test cases before merging. Added to gap registry as G-033.
- **Indexer batch SELECT:** Per-track `WHERE track_id = ?` in `indexer._index_rows()` could be batched to `IN (...)` — low priority given indexing is infrequent.
- **Scanner upsert helper:** Duplicate UPDATE/INSERT SQL in `scan_library()`/`scan_paths()` — cosmetic refactor, no correctness issue.

---

## Files Changed

`oracle/worker.py`, `oracle/acquirers/guard.py`, `oracle/acquirers/waterfall.py`, `oracle/acquirers/smart_pipeline.py`, `oracle/acquirers/realdebrid.py`, `oracle/acquirers/spotdl.py`, `oracle/acquirers/ytdlp.py`, `oracle/acquirers/qobuz.py`, `oracle/acquirers/streamrip.py` (new), `oracle/scorer.py`, `oracle/radio.py`, `oracle/normalizer.py`, `oracle/vibes.py`, `oracle/ingest_watcher.py`, `oracle/api/blueprints/acquire.py`, `oracle/db/schema.py`, `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/SESSION_INDEX.md`
