# Session Log - S-20260309-05

**Date:** 2026-03-09
**Goal:** Segregate active vs historical files by moving non-active tracked artifacts into archive and normalize root layout
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

The repo root still contained multiple legacy runtime and historical assets mixed with
canonical runtime surfaces. Legacy files were tracked but not segregated under a single
archival path.

---

## Work Done

Bullet list of completed work:

- [x] Created tracked archive hierarchy at `archive/` with explicit purpose sections.
- [x] Moved legacy runtime scripts and historical exports into `archive/legacy-runtime/`.
- [x] Moved legacy Docker assets into `archive/legacy-ops/`.
- [x] Moved one-off historical report into `archive/historical-docs/`.
- [x] Moved prior `_archive` snapshot content into `archive/legacy-archive/`.
- [x] Moved `lyra_api.py` into `archive/legacy-runtime/lyra_api.py`.
- [x] Moved the full `oracle/` legacy runtime tree into `archive/legacy-runtime/oracle/`.
- [x] Moved Python tests into `archive/legacy-runtime/tests-python/`.
- [x] Moved legacy Python utility scripts into `archive/legacy-runtime/scripts/`.
- [x] Updated `.gitignore` policy to stop ignoring `_archive` and keep archive history tracked.
- [x] Updated `scripts/ensure_workspace_docker.ps1` to use archived docker-compose location.
- [x] Updated `scripts/build_backend_sidecar.ps1` and `scripts/build_runtime_tools.ps1` to use archived Python entrypoints.
- [x] Updated canonical-path docs to reflect archive placement.
- [x] Added `archive/INVENTORY.md` with full move manifest (`what was -> what is`) and archive category inventory.
- [x] Verified no `.py` files remain outside `archive/`.

---

## Commits

| SHA (short) | Message |
|---|---|
| `dad2a3f` | `[S-20260309-05] refactor: normalize root and archive legacy artifacts` |
| `fa0d377` | `[S-20260309-05] refactor: archive all legacy python surfaces` |
| `(pending)` | `[S-20260309-05] docs: add archive inventory ledger` |

---

## Key Files Changed

- `archive/README.md` - defines archive policy and layout.
- `archive/INVENTORY.md` - inventory ledger of archived files, markdown records, and move manifest.
- `archive/legacy-runtime/*` - relocated legacy runtime scripts and historical exports.
- `archive/legacy-runtime/oracle/*` - relocated full legacy Python source tree.
- `archive/legacy-runtime/tests-python/*` - relocated Python test suite.
- `archive/legacy-ops/*` - relocated non-canonical Docker assets.
- `scripts/ensure_workspace_docker.ps1` - points to `archive/legacy-ops/docker-compose.yml`.
- `scripts/build_backend_sidecar.ps1` - points to `archive/legacy-runtime/lyra_api.py`.
- `scripts/build_runtime_tools.ps1` - points to `archive/legacy-runtime/scripts/`.
- `.gitignore` - removed `_archive` archive-ignore behavior; kept runtime-secret ignore scope.
- `docs/CANONICAL_PATHS.md` - updated legacy/reference path mapping.

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Yes. Historical and non-canonical runtime artifacts are now segregated under a tracked
`archive/` tree instead of being mixed through repo root, and tracked Python files are now
fully archived under `archive/legacy-runtime/`.

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1`

---

## Next Action

What is the single most important thing to do next?

Continue normalizing historical doc references so they explicitly point to
`archive/legacy-runtime/` paths where useful.

