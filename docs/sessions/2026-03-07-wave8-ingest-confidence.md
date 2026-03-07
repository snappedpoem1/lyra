# Session S-20260307-08 — Wave 8: Ingest Confidence + Normalization

**Date:** 2026-03-07
**Agent:** GitHub Copilot (Claude Sonnet 4.6)
**Goal:** Implement the SPEC-007 ingest-confidence lifecycle state machine end-to-end

---

## Work Completed

### 1. SPEC-007 (carried from prior session)
- `docs/specs/SPEC-007_INGEST_CONFIDENCE.md` — full spec: lifecycle states, reason codes per stage, DB contract, API contract, doctor surface, backfill rule

### 2. State Machine Module
- `oracle/ingest_confidence.py` — complete state machine
  - `record_transition(filepath, state, reason_codes, track_id, source)`
  - `backfill_placed_tracks()` — seeds `placed` rows for all existing library tracks at startup
  - `get_confidence_summary()` — aggregate counts + stall detection
  - `get_recent_transitions(limit)` — newest-first transition list

### 3. DB Schema
- `oracle/db/schema.py` — added `ingest_confidence` table DDL + 4 indexes

### 4. `_native_ingest` Hook
- `oracle/ingest_watcher.py` `_native_ingest()` — wired `record_transition` at each pipeline stage:
  - Before guard: `acquired / file_detected`
  - Guard pass: `validated / guard_pass`
  - Guard reject: `rejected / guard_duplicate | guard_junk | guard_label`
  - After `shutil.move`: `normalized / normalized_name, moved_to_library`
  - After scan: `enriched / enrichment_skipped` (source for enrichment_skipped: no external enricher in vanilla ingest)
  - After index: `placed / scan_complete [+ embedding_indexed, scored]`
  - Built `path_to_track_id` map via post-scan DB query

### 5. API Blueprint
- `oracle/api/blueprints/ingest.py` — `GET /api/ingest/confidence/summary`, `GET /api/ingest/confidence/recent?limit=N`
- `oracle/api/registry.py` — `ingest` blueprint added to `BLUEPRINTS` manifest

### 6. Doctor Integration
- `oracle/doctor.py` — `_check_ingest_confidence()` added; surfaced in `run_doctor()` return list
- Reports: `{N placed} / {N rejected} / {N stalled} (backfill {N})`; WARNING if stalled > 0

### 7. Startup Backfill
- `oracle/api/app.py` — `backfill_placed_tracks()` called at end of `create_app()`; runs once per startup, logs count if > 0

### 8. Tests
- `tests/test_ingest_confidence.py` — 14 tests covering:
  - `record_transition` (writes row, unknown state rejected, multi-state, rejected state)
  - `backfill_placed_tracks` (creates placed rows, no duplicate backfill, empty table)
  - `get_confidence_summary` (empty db, state counts, stall detection)
  - `get_recent_transitions` (newest-first ORDER BY, limit respected, reason_codes deserialized)
- Test isolation: in-memory SQLite with `_NoCloseProxy` pattern to prevent shared-connection teardown

---

## Validation

```
.venv\Scripts\python.exe -m pytest tests/test_ingest_confidence.py -v  →  14 passed
.venv\Scripts\python.exe -m pytest -q                                   →  167 passed
```

---

## Files Modified

| File | Change |
|------|--------|
| `docs/specs/SPEC-007_INGEST_CONFIDENCE.md` | Created (prior session) |
| `oracle/ingest_confidence.py` | Created (prior session) |
| `oracle/db/schema.py` | `ingest_confidence` table + indexes (prior session) |
| `oracle/ingest_watcher.py` | `_native_ingest` wired with `record_transition` at 5 stages |
| `oracle/api/blueprints/ingest.py` | Created — confidence summary + recent endpoints |
| `oracle/api/registry.py` | `ingest` blueprint added to manifest |
| `oracle/doctor.py` | `_check_ingest_confidence` added + wired into `run_doctor` |
| `oracle/api/app.py` | `backfill_placed_tracks()` called at startup |
| `tests/test_ingest_confidence.py` | Created — 14 tests |
| `docs/PROJECT_STATE.md` | Sections 1, 2, 4, 6, 7 updated for Wave 8 |
| `docs/PHASE_EXECUTION_COMPANION.md` | Wave 7 status filled; Wave 8 status filled; gap entries updated |
| `docs/WORKLIST.md` | In Progress + Next Up updated |
| `docs/SESSION_INDEX.md` | S-20260307-08 row added |

---

## Active Gaps Leaving This Session

1. Blank-machine installer proof — blocked-external
2. Full 4-hour parity soak — deferred
3. Dev data root migration — not yet migrated with library data
4. Historical ingest events (pre-Wave 8 tracks) have backfill `placed` rows only; `normalized`/`enriched` states are not reconstructed for historical events

---

## Next Action

Open Wave 9 (Scout + Community Weather) per `docs/PHASE_EXECUTION_COMPANION.md`:
1. Write `docs/specs/SPEC-008_SCOUT_COMMUNITY_WEATHER.md` first
2. Then implement per spec
