# Session Log - S-20260305-05

**Date:** 2026-03-05  
**Goal:** Fix open gaps one-by-one, capture breakthroughs, and reset TODO/gap lists  
**Agent(s):** Codex

---

## Context

Gap audit (S-20260305-04) identified remaining missing parts:

- pipeline resume-by-job-id path was explicitly unimplemented
- streamrip tier was a hard stub
- ListenBrainz discovery path had known `0 queued` behavior
- title cleaning was split across guard/scanner/name_cleaner
- docs lists needed reset after closures

---

## Work Done

- Implemented pipeline job-id resume semantics in `oracle/pipeline.py`
  - completed/running job IDs now return cached status
  - requested/failed job IDs now resume instead of deprecated rerun warning
- Replaced streamrip stub with executable adapter in `oracle/acquirers/streamrip.py`
  - CLI discovery (`rip`) + command execution + output file detection
  - config support via `LYRA_STREAMRIP_BINARY` and `LYRA_STREAMRIP_CMD_TEMPLATE`
- Consolidated title cleaning entry points:
  - `oracle/scanner.py` now routes `_deep_clean_title()` through `name_cleaner.clean_title_str()`
  - `oracle/acquirers/guard.py` now routes `_clean_title()` through the same canonical cleaner
  - added `clean_title_str()` to `oracle/name_cleaner.py`
- Fixed ListenBrainz community discovery parser in `oracle/integrations/listenbrainz.py`
  - API list-shaped payloads now parsed correctly
  - added strict local cap to `count` after parse (including cached payload path)
  - validation run now queues non-zero items (`27` with `--limit-artists 12 --tracks-per-artist 5`)
- Validated structure analysis runtime:
  - ran `python -m oracle structure analyze --limit 50`
  - `track_structure` row count increased (`13 -> 61`)
- Added tests:
  - `tests/test_pipeline_wrapper.py` expanded with resume behavior
  - `tests/test_streamrip.py` for availability/download paths
  - `tests/test_listenbrainz_parser.py` for API payload normalization
- Refreshed operational docs so backlog can restart cleanly:
  - `docs/TODO.md` reset to unresolved items only
  - `docs/MISSING_FEATURES_REGISTRY.md` rewritten with closed gaps removed and new state
  - `docs/WORKLIST.md` updated with breakthroughs and marker progress
  - `docs/PROJECT_STATE.md` updated with latest metrics/test count

---

## Commits

| SHA (short) | Message |
|---|---|
| `pending` | `[S-20260305-05] fix: close major gaps and reset operational backlog` |

---

## Key Files Changed

- `oracle/pipeline.py` - real resume handling for existing job IDs
- `oracle/acquirers/streamrip.py` - executable tier-2 adapter replacing stub
- `oracle/integrations/listenbrainz.py` - payload parser and count cap fix
- `oracle/scanner.py`, `oracle/acquirers/guard.py`, `oracle/name_cleaner.py` - title cleaner consolidation
- `tests/test_pipeline_wrapper.py`, `tests/test_streamrip.py`, `tests/test_listenbrainz_parser.py` - regression coverage
- `docs/TODO.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/WORKLIST.md`, `docs/PROJECT_STATE.md` - backlog/state reset

---

## Result

Multiple previously open gaps were closed in one sweep:

- pipeline resume path is no longer unimplemented
- ListenBrainz community discovery no longer zero-yields
- title-clean divergence between scanner/guard/name_cleaner is removed
- structure analysis is actively writing rows in current runtime
- backlog docs were reset so new findings can be captured cleanly

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Install/configure streamrip CLI on this machine and verify one successful tier-2 waterfall acquisition to fully retire the remaining streamrip availability gap.
