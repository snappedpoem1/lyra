# Session Log - S-20260306-19

**Date:** 2026-03-06
**Goal:** Advance runtime/source separation without touching installer or soak lanes
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

The repo had already moved packaged sidecar/runtime helper staging into `.lyra-build/bin`,
but generated artifacts still leaked into repo-root paths in several places. In particular:

- `oracle.config` still resolved frozen `PROJECT_ROOT` from `Path.cwd()` instead of
  `Path(sys.executable).parent`
- packaged host/backend logs still defaulted into `logs/`
- default HuggingFace cache roots still targeted repo-root `hf_cache`
- runtime pause/profile files still wrote directly into repo-root dotfiles
- `oracle.doctor` used a repo-root temp write probe

---

## Work Done

Bullet list of completed work:

- [x] Fixed frozen-root drift by making `oracle.config` resolve packaged `PROJECT_ROOT`
  from `Path(sys.executable).parent`, matching `lyra_api.py`
- [x] Added config-owned generated-path roots for build/log/temp/state/model-cache paths
  under `.lyra-build`
- [x] Updated `lyra_api.py`, `oracle/api/app.py`, `oracle/worker.py`, and
  `oracle/embedders/clap_embedder.py` to use config-owned model-cache defaults
- [x] Updated `oracle/runtime_state.py` to write new state files under
  `.lyra-build/state` while preserving legacy repo-root read compatibility
- [x] Moved packaged host/debug-sidecar log defaults behind `.lyra-build/logs/*`
- [x] Added focused tests for frozen-root resolution, generated-dir creation, and
  runtime-state compatibility
- [x] Revalidated backend test suite and doctor output

---

## Commits

| SHA (short) | Message |
|---|---|
| `pending` | `[S-20260306-19] feat: advance runtime source separation defaults` |
| `pending` | `[S-20260306-19] docs: record runtime source separation pass` |

---

## Key Files Changed

- `oracle/config.py` - added explicit generated-path roots and fixed frozen root resolution
- `lyra_api.py` - switched packaged backend logging and model-cache defaults to config-owned roots
- `oracle/api/app.py` - aligned HuggingFace cache env setup with config-owned model-cache roots
- `oracle/runtime_state.py` - moved new runtime state writes under `.lyra-build/state` with legacy fallback reads
- `oracle/doctor.py` - moved the write probe into config-owned temp scratch space
- `oracle/worker.py` - aligned worker-side HuggingFace cache defaults with config-owned roots
- `oracle/embedders/clap_embedder.py` - defaulted local CLAP cache to config-owned generated roots
- `scripts/start_lyra_unified.ps1` - exported `.lyra-build` log/temp/state/cache roots for packaged host runs
- `scripts/debug_sidecar_boot.ps1` - moved debug-sidecar log output under `.lyra-build/logs`
- `tests/test_runtime_services_policy.py` - added frozen-root and generated-dir coverage
- `tests/test_runtime_state.py` - added runtime-state migration/compat coverage
- `docs/PROJECT_STATE.md` - updated runtime/source-separation truth and verification results

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Yes. Lyra now has a real first-pass split between source files and runtime-generated
artifacts: frozen installs resolve the same root consistently, and the default
generated outputs for logs, temp scratch, runtime state, and model cache no longer
target the repo root. The gap is still partial because persistent data roots and a
few broader path assumptions remain, but the generated-artifact layer is materially
cleaner and better aligned with installed layouts.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

What is the single most important thing to do next?

Finish the blank-machine installer proof, then execute the 4-hour parity soak, then
return to the next runtime/source-separation pass for remaining persistent-path cleanup.
