# Session Log - S-20260306-14

**Date:** 2026-03-06
**Goal:** Harden parity soak validation into a real runtime stability proof
**Agent(s):** Codex / Manual

---

## Context

Session `S-20260306-13` had already added installed-layout validation and
packaged runtime-root hardening, but the release-gate soak path was still too
thin. The parity script mostly polled player state, and packaged proof scripts
could still pass against an unrelated backend already occupying port `5000`.

---

## Work Done

- Rebuilt `scripts/parity_hardening_acceptance.ps1` into a real mutating soak
  runner:
  - writes timestamped log and JSONL snapshot artifacts under
    `.lyra-build/logs/parity`
  - claims a deterministic sidecar backend before validation
  - performs forced restart recovery assertions
  - runs periodic pause/resume, seek, next/previous, and mode mutations during
    soak
  - captures failure diagnostics automatically
- Fixed frozen sidecar completeness in `scripts/build_backend_sidecar.ps1` by
  adding explicit hidden imports for `oracle.api.blueprints.*` and related API
  modules so the PyInstaller onefile build exposes the real Flask routes.
- Hardened `scripts/packaged_host_smoke.ps1` so it stops any pre-existing
  backend listener before launch, preventing false-positive packaged-host smoke
  passes.
- Revalidated the corrected sidecar and packaged proof path:
  - `build_backend_sidecar.ps1` launch check passed
  - `packaged_host_smoke.ps1` passed after claiming a fresh backend
  - the new parity soak runner passed a short mutation/checkpoint run

---

## Commits

| SHA (short) | Message |
|---|---|
| `3432c56` | `[S-20260306-14] feat: harden packaged proof and parity soak runtime gates` |
| `pending` | `[S-20260306-14] docs: record soak runtime hardening state` |

---

## Key Files Changed

- `scripts/build_backend_sidecar.ps1` - explicitly bundles blueprint modules in
  the frozen sidecar so launch checks validate the real API
- `scripts/packaged_host_smoke.ps1` - claims port `5000` before packaged-host
  smoke so validation is deterministic
- `scripts/parity_hardening_acceptance.ps1` - adds artifact logging, checkpoint
  snapshots, mutation cadence, and restart-hardened sidecar control
- `docs/PROJECT_STATE.md` - recorded corrected sidecar/packaged-proof truth
- `docs/WORKLIST.md` - moved the hardened 4-hour soak command into the active
  next-up lane
- `docs/MISSING_FEATURES_REGISTRY.md` - updated G-035 and G-036 evidence

---

## Result

The frozen sidecar now launches with the full API contract instead of a
blueprint-less stub, packaged-host smoke is no longer vulnerable to an existing
backend masking failures, and parity hardening now produces real soak evidence
instead of a passive state poll.

What remains is external validation, not local ambiguity:

- blank-machine installer install-and-launch proof
- full 4-hour parity soak
- real-device native audio confidence beyond the short local mutation run

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row updated
- [x] Tests pass: `python -m pytest -q`

---

## Verification

- `powershell -ExecutionPolicy Bypass -File scripts\build_backend_sidecar.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\packaged_host_smoke.ps1 -HealthTimeoutSeconds 45`
- `powershell -ExecutionPolicy Bypass -File scripts\validate_clean_machine_install.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\validate_installed_runtime.ps1 -InstalledRoot desktop\renderer-app\src-tauri\target\debug -HealthTimeoutSeconds 45`
- `powershell -ExecutionPolicy Bypass -File scripts\parity_hardening_acceptance.ps1 -SkipSidecarBuild -SkipInstallerProof -SoakSeconds 45 -CheckpointIntervalSeconds 10 -ActionIntervalSeconds 8 -StartupTimeoutSeconds 60`
- `.venv\Scripts\python.exe -m pytest -q`

---

## Next Action

Run the installer on a truly blank Windows machine, then execute the hardened
parity command as a full 4-hour soak:

`powershell -ExecutionPolicy Bypass -File scripts\parity_hardening_acceptance.ps1 -SkipSidecarBuild -CheckpointIntervalSeconds 300 -ActionIntervalSeconds 120 -SoakSeconds 14400`
