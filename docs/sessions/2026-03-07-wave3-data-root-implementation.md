# Session Log - S-20260307-02

**Date:** 2026-03-07
**Goal:** Implement LYRA_DATA_ROOT authority and finish the Wave 3 runtime path contract
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

---

## Work Done

Bullet list of completed work:

- [x] Implemented authoritative `LYRA_DATA_ROOT` resolution in `oracle.config` with dev default `%LOCALAPPDATA%\Lyra\dev`, frozen default `%LOCALAPPDATA%\Lyra`, explicit legacy detection, and opt-in legacy fallback via `LYRA_USE_LEGACY_DATA_ROOT=1`.
- [x] Cut backend/runtime consumers over to config-owned data roots: startup, worker, doctor, runtime state, ingest watcher, Chroma users, CLI/status surfaces, and packaged-host launch helpers.
- [x] Added strict validation and regression coverage for the data-root contract, including isolated dev/frozen probes and legacy-state behavior.
- [x] Reconciled repo truth docs for the Wave 3 landing and the remaining closeout scope.

---

## Commits

| SHA (short) | Message |
|---|---|
| `xxxxxxx` | `S-20260307-02 type: description` |

---

## Key Files Changed

- `oracle/config.py` - introduced authoritative data-root resolution, derived writable paths, legacy detection helpers, and shared directory creation.
- `lyra_api.py` - switched startup logging/cache setup to config-owned roots and surfaced legacy-data warnings during boot.
- `oracle/api/app.py` - aligned Flask startup cache/bootstrap handling with the new data-root contract.
- `oracle/worker.py` - moved worker cache/bootstrap setup onto data-root derived paths.
- `oracle/doctor.py` - made diagnostics aware of migration-needed state and new writable roots.
- `oracle/db/schema.py` - ensures the derived database directory exists before first connect.
- `oracle/runtime_state.py` - keeps compatibility reads but writes profile/pause state under the active data root.
- `oracle/ingest_watcher.py` - moved watcher lock state under the config-owned state root.
- `oracle/chroma_store.py`, `oracle/indexer.py`, `oracle/scorer.py` - removed hardcoded repo-root Chroma defaults.
- `oracle/cli.py`, `oracle/curator.py`, `oracle/api/blueprints/library.py`, `oracle/api/blueprints/vibes.py`, `oracle/status.py` - aligned user-entry/runtime status surfaces with the new contract.
- `scripts/start_lyra_unified.ps1`, `scripts/validate_data_root_contract.ps1` - packaged host now uses isolated data-root overrides and the validator now checks dev, override, and frozen layouts.
- `tests/test_config_data_root.py`, `tests/test_runtime_services_policy.py` - regression coverage for the new contract.
- `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/SESSION_INDEX.md` - repo truth updates for the Wave 3 landing.

---

## Result

Wave 3's core runtime contract is now live. Lyra no longer silently writes its runtime database, Chroma store, logs, temp files, state, model cache, staging, and downloads into repo-root defaults; those now resolve from `LYRA_DATA_ROOT`, and the contract is validated for dev, frozen, and explicit override scenarios. The remaining Wave 3 work is the user-facing migrate-now/defer flow plus blank-machine confirmation against the new contract.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Implement the explicit migrate-now/defer copy flow for legacy repo-root data, then run the blank-machine installer proof against the finalized data-root contract.
