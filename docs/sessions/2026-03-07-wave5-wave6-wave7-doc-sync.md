# Session S-20260307-07 — Wave 5+6 Completion Doc Sync and Wave 7 Blocked Items

## Session ID

S-20260307-07

## Date

2026-03-07

## Goal

Record Wave 5 (Provider Contract and Recommendation Core) and Wave 6 (Product Explainability Surfaces) as locally landed, document the Wave 7 packaged host smoke baseline, and record the parity soak constraint for the frozen sidecar.

## Context

This session continues from an interrupted previous session. Before this session, the following had been validated:

- **153 backend tests passing**
- **Renderer TypeScript zero type errors** (`npx tsc --noEmit`)
- **Renderer build passes clean** (`npm run build`)
- **Packaged host smoke passes** (`scripts/packaged_host_smoke.ps1 -AllowExistingBackend`)
- **Parity soak attempt blocked** — frozen sidecar at `.lyra-build/bin/lyra_backend.exe` was built before Wave 5+6 changes and exits with code 1; soak needs a sidecar rebuild

The previous session also:
- Extended `scripts/parity_hardening_acceptance.ps1` with a `-DataRoot` parameter so the soak can target the dev database without requiring a frozen sidecar rebuild
- Began editing PROJECT_STATE.md Wave 5+6 entries before being cut off

## What Was Done This Session

1. **PROJECT_STATE.md** — completed the Wave 5+6 doc sync:
   - Section 1 program state already updated by prior session
   - Section 2 Oracle/recommendation state block already updated by prior session
   - Section 4 verification results already updated by prior session (153 passed, packaged host smoke Wave 7 baseline)
   - Section 5 documentation truth was already updated
   - **Section 6 Active Gaps** — updated to reflect Wave 5+6 landed; added sidecar rebuild constraint for parity soak
   - **Section 7 Immediate Next Pass** — updated from "Open Wave 5" to Wave 7 closeout priorities

2. **ROADMAP_ENGINE_TO_ENTITY.md** — marked Waves 5 and 6 as `(landed locally)` and Wave 7 as `(active)` with blocked-item detail

3. **PHASE_EXECUTION_COMPANION.md**:
   - Section 2 baseline updated from "Waves 1–4 landed" to "Waves 1–6 landed" with Wave 5 and 6 closeout summaries
   - Wave 5 status field added: `landed locally`
   - Wave 6 status field added: `landed locally`
   - Wave 7 status field added: `active; packaged host smoke passes; frozen sidecar requires rebuild for parity soak; blank-machine proof blocked-external; 4-hour soak deferred`

4. **WORKLIST.md**:
   - Wave 5+6 completion entries added to Completed Recently
   - Wave 7 baseline validation outcome documented (packaged smoke pass, parity soak constraint)
   - In Progress section updated to this session
   - Next Up updated from "Open Wave 5" to Wave 7+8 priorities

5. **SESSION_INDEX.md** — added row for S-20260307-07

## Owned Files

- `docs/PROJECT_STATE.md` (sections 6–7)
- `docs/ROADMAP_ENGINE_TO_ENTITY.md` (Wave 5–7)
- `docs/PHASE_EXECUTION_COMPANION.md` (baseline + Wave 5–7 status)
- `docs/WORKLIST.md` (completed recently + in progress + next up)
- `docs/SESSION_INDEX.md` (new row)
- `docs/sessions/2026-03-07-wave5-wave6-wave7-doc-sync.md`

## Forbidden Files (not touched this session)

- Any `oracle/` implementation files
- Any `desktop/renderer-app/` files
- `scripts/parity_hardening_acceptance.ps1` (already modified by previous session)

## Wave 7 Blocked Items (with Evidence)

### 7A — Packaged Host Smoke

**Status: PASS**

```
[packaged-host-smoke] running debug packaged-host launch smoke
[lyra-unified] starting packaged host: C:\MusicOracle\desktop\renderer-app\src-tauri\target\debug\Lyra Oracle.exe
[lyra-unified] waiting for backend health readiness
[lyra-unified] Lyra unified launch ready (frontend + backend active)
[lyra-unified] leaving host process running (pid: 26980)
[packaged-host-smoke] stopping packaged host process tree (26980)
[packaged-host-smoke] packaged host smoke passed
```

### 7B — 4-Hour Parity Soak

**Status: BLOCKED (sidecar rebuild required)**

Immediate failure reason: the frozen sidecar `.lyra-build/bin/lyra_backend.exe` was built before Wave 5+6. When launched, it exits with code 1 before reaching health readiness. The sidecar needs to be rebuilt via `scripts/build_backend_sidecar.ps1` to include `oracle/provider_contract.py`, `oracle/provider_health.py`, and the updated `oracle/recommendation_broker.py`.

The soak script was also extended with `-DataRoot` so it can target the dev database (`%LOCALAPPDATA%\Lyra\dev`) without requiring a full frozen sidecar rebuild for dev-mode validation. However, even the dev-backend path hit a "no such table: tracks" error when the sidecar defaulted to an empty `%LOCALAPPDATA%\Lyra` root.

Corrective path:
1. Rebuild sidecar: `powershell -ExecutionPolicy Bypass -File scripts/build_backend_sidecar.ps1`
2. Run soak: `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 14400 -StartupTimeoutSeconds 60`

### 7A-parallel — Blank-Machine Installer Proof

**Status: BLOCKED (no clean Windows machine or VM available)**

Evidence: clean-machine artifact proof, simulated install layout, and installed-layout validation all pass locally, but a true blank-machine first-install test requires a VM or separate physical machine that is not currently available.

## Result

All Wave 5, Wave 6, and Wave 7 documentation is now synchronized with the validated local repo state. The implementation work is complete; the remaining Wave 7 gap is mechanical (sidecar rebuild) and external (blank-machine VM).

## Next Action

1. Run `scripts/build_backend_sidecar.ps1` to rebuild the frozen sidecar with Wave 5+6 modules.
2. Run the parity soak against the rebuilt sidecar.
3. Open Wave 8 after parity soak passes.
