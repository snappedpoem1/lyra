# Session Log - S-20260306-13

**Date:** 2026-03-06
**Goal:** Advance blank-machine installer validation and packaged runtime hardening, validate, commit, and push
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

The release gate had moved past static artifact staging, but the blank-machine installer lane still lacked two practical pieces:

- a reusable installed-app validation script that can be handed to a clean Windows machine or VM
- stronger packaged runtime-root resolution for installed sidecar layouts

Parallel work in the same workspace also closed the live packaged streamrip proof and added Spotify import background endpoints, so this session had to normalize docs against the actual verified workspace state rather than stale session boundaries.

---

## Work Done

- Added `scripts/validate_installed_runtime.ps1` to validate installed or installed-style app roots, detect host/sidecar/runtime-tool layouts, and optionally smoke-launch the installed host via `LYRA_PACKAGED_HOST_EXE`.
- Extended `scripts/packaged_host_smoke.ps1` with `-HostExe` support so it can target an installed app directly instead of only the repo-local debug host.
- Hardened packaged runtime-root resolution in `desktop/renderer-app/src-tauri/src/main.rs` so installed layouts resolve `runtime/bin` correctly when the sidecar is located under `bin`, `resources`, or `resources/bin`.
- Rebuilt the Tauri debug bundles and validated:
  - clean-machine artifact proof
  - packaged host smoke
  - installed-layout validation against the rebuilt debug host
- Reconciled docs to the actual verified workspace state:
  - live packaged streamrip acquisition is closed (`G-034`)
  - installer completeness remains partial pending a true blank-machine install and first-launch proof
  - backend suite is now `106 passed`

---

## Commits

| SHA (short) | Message |
|---|---|
| `930f290` | `[S-20260306-13] feat: harden installed runtime validation` |
| `pending` | `[S-20260306-13] docs: record installed runtime validation state` |

---

## Key Files Changed

- `scripts/validate_installed_runtime.ps1` - new installed-app validation path for blank-machine and installed-layout proof
- `scripts/packaged_host_smoke.ps1` - explicit installed host targeting via `-HostExe`
- `desktop/renderer-app/src-tauri/src/main.rs` - packaged runtime-root anchor resolution hardened for installed layouts
- `docs/PROJECT_STATE.md` - normalized current runtime truth and verification state
- `docs/WORKLIST.md` - updated active execution ordering after live streamrip closure and installed-layout validation
- `docs/MISSING_FEATURES_REGISTRY.md` - closed `G-034`, advanced `G-035`, and refreshed remaining gaps

---

## Result

The installer lane is tighter than it was at session start. Lyra now has a reusable validation script for installed app roots and a more defensive packaged runtime resolver for installed layouts. The rebuilt debug host passes installed-layout validation, which gives the blank-machine lane a practical handoff path instead of relying only on repo-local debug assumptions.

The remaining installer gap is now explicit: a true blank-machine install and first launch outside this workstation.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Run a real blank-machine installer install-and-launch validation on a clean Windows VM, then execute the 4-hour parity-hardening soak.
