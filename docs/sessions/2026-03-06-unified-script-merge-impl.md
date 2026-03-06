# Session Log - S-20260306-07

**Date:** 2026-03-06
**Goal:** Implement unified backend+frontend launcher with no Docker dependency
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

- Tauri/backend-player cutover was already active, but startup paths were split
  (`desktop` npm scripts + legacy `scripts/dev_desktop.ps1`) and operator flow was not
  locked to one canonical launcher.
- User requested a script merge where backend + frontend are active together with
  no Docker startup dependency, plus acquisition treated as optional/non-blocking.

---

## Work Done

Bullet list of completed work:

- [x] Added canonical launcher script: `scripts/start_lyra_unified.ps1`.
  - Interface: `-Mode dev|packaged`, `-HealthTimeoutSeconds`, `-LeaveRunning`, `-SkipSidecarBuild`.
  - Dev mode starts Tauri host (`desktop -> npm run dev`) and health-gates on `/api/health`.
  - Packaged mode validates sidecar build (unless skipped) and launches packaged host binary when present.
  - Reuse behavior: if backend is already healthy, launch proceeds without backend restart.
  - Docker startup is never invoked.
- [x] Deprecated duplicate launcher path:
  - `scripts/dev_desktop.ps1` now delegates to `scripts/start_lyra_unified.ps1`.
  - Added desktop npm alias: `desktop/package.json -> start:unified`.
- [x] Added backend acquisition bootstrap status surface:
  - New module: `oracle/acquirers/bootstrap_status.py`.
  - Background snapshot refresh from waterfall tier checks on API app startup.
  - `/api/health` and `/api/status` now include `acquisition` snapshot payload.
  - Unified UI Oracle pane now renders acquisition tier readiness/degraded summary.
- [x] Updated docs/operator contract:
  - `README.md` quick start now points to unified launcher.
  - Added “What starts / What does not start” runbook section.
  - Updated `docs/PROJECT_STATE.md` and `docs/WORKLIST.md` with canonical launcher + no-Docker policy.
- [x] Validation completed:
  - `python -m pytest -q` (88 passed)
  - `cd desktop/renderer-app; npm run test` (pass)
  - `cd desktop/renderer-app; npm run build` (pass)
  - `scripts/smoke_step1_step2.ps1 -SkipSidecarBuild` (pass)
  - Hardened smoke/parity cleanup to stop PyInstaller sidecar process trees (no lingering backend listeners)
  - Unified launcher warm path: `start_lyra_unified.ps1 -Mode dev -LeaveRunning` (pass)
  - Unified launcher cold path: `start_lyra_unified.ps1 -Mode dev -LeaveRunning` with no listener on :5000 (pass)
  - Failure path: `start_lyra_unified.ps1 -Mode packaged -SkipSidecarBuild` returns non-zero with clear packaged-host-missing error
  - `scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -StartupTimeoutSeconds 60 -SoakSeconds 10` (pass after cleanup hardening)
  - Sidecar build refreshed with current code: `scripts/build_backend_sidecar.ps1 -SkipLaunchCheck`

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | Local working session (no commit yet) |

---

## Key Files Changed

- `scripts/start_lyra_unified.ps1` - canonical unified startup path.
- `scripts/dev_desktop.ps1` - deprecated wrapper delegating to unified launcher.
- `scripts/smoke_step1_step2.ps1`, `scripts/parity_hardening_acceptance.ps1` - process-tree cleanup to prevent lingering sidecar listeners.
- `desktop/package.json` - unified launcher alias.
- `oracle/acquirers/bootstrap_status.py` - non-blocking acquisition tier snapshot bootstrap.
- `oracle/api/app.py` - startup hook for acquisition snapshot refresh.
- `oracle/api/blueprints/core.py` - health/status payload includes acquisition snapshot.
- `desktop/renderer-app/src/services/lyraGateway/queries.ts`, `desktop/renderer-app/src/app/UnifiedWorkspace.tsx` - UI/status surface for acquisition tier readiness/degraded state.
- `README.md`, `docs/PROJECT_STATE.md`, `docs/WORKLIST.md` - operator contract and state updates.

---

## Result

Yes. Lyra now has one canonical startup script for backend + frontend, no Docker
auto-start dependency, and health/status visibility for acquisition tier availability
as a non-blocking startup surface.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Run clean-machine packaged installer validation for `lyra_backend.exe` + packaged host,
then execute 4-hour native audio soak acceptance.

