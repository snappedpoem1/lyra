# Session Log - S-20260307-25

**Date:** 2026-03-07
**Goal:** Fix packaged desktop backend handshake and CORS so installed webviews can connect to the local backend reliably
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

- The user still saw the frontend `Backend Not Ready` overlay with `Failed to fetch` even after prior installer rebuilds.
- Local packaged-host smoke could launch the backend, so the remaining suspect boundary was the installed webview talking to the bundled backend rather than compilation or sidecar existence.

---

## Work Done

Bullet list of completed work:

- [x] Reproduced the packaged runtime path via `scripts/validate_installed_runtime.ps1` against a simulated installed layout under `.tmp`.
- [x] Identified that packaged launches could still inherit the repo working directory and resolve the wrong runtime/project root for installed apps.
- [x] Updated `desktop/renderer-app/src-tauri/src/main.rs` so packaged backend launches always anchor from the bundled sidecar/runtime path unless `LYRA_PROJECT_ROOT` is explicitly set.
- [x] Updated `scripts/start_lyra_unified.ps1` so packaged host smoke launches installed apps from the installed app directory instead of the repo root.
- [x] Identified a separate frontend boundary issue: backend CORS defaults only allowed Vite dev origins and ignored `/ws/*`.
- [x] Expanded backend CORS defaults in `oracle/api/cors.py` to allow common Tauri packaged origins and `/ws/*`.
- [x] Added regression coverage in `tests/test_api_cors.py` for both `/api/health` and `/ws/player`.
- [x] Rebuilt the NSIS installer after the runtime-root and CORS fixes.

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | `local changes (no commit yet)` |

---

## Key Files Changed

- `desktop/renderer-app/src-tauri/src/main.rs` - fixed packaged backend runtime-root resolution so installed launches do not fall back to repo-root context.
- `desktop/renderer-app/src-tauri/tauri.conf.json` - packaged window scheme toggled during debugging to reduce mixed-content risk while isolating the frontend handshake boundary.
- `scripts/start_lyra_unified.ps1` - launches packaged hosts from the installed app directory for installed-layout proofs.
- `oracle/api/cors.py` - default CORS origins now include Tauri packaged origins and `/ws/*` SSE coverage.
- `tests/test_api_cors.py` - regression tests for packaged-origin API and SSE access.
- `docs/SESSION_INDEX.md` - corrected the duplicate session ID and recorded the actual work.

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

- Installed-layout runtime validation now passes end to end, including the `LOCALAPPDATA` data-root contract proof.
- Backend CORS now permits the packaged Tauri webview origin for both API calls and player SSE.
- A fresh NSIS installer was rebuilt after both the packaged host/runtime fix and the backend CORS fix.
- Despite those local proofs, the user reported that the rebuilt real installer still showed the same frontend error, so this session improved the packaged runtime path but did not close the installed-app failure end to end.

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: targeted validation (`cargo check`, `npm run build`, `.venv\Scripts\python.exe -m pytest -q tests\test_api_cors.py`, `powershell -ExecutionPolicy Bypass -File scripts\validate_installed_runtime.ps1 -InstalledRoot .tmp\installed-app-smoke-current -HealthTimeoutSeconds 75`, `npm run tauri:build:fast:nsis`)

---

## Next Action

What is the single most important thing to do next?

- Capture the failing installed-app host boot log and backend log from the user’s real installer run, then compare that evidence against the passing local installed-layout proof.
