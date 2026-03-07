# Session Log - S-20260306-23

**Date:** 2026-03-06
**Goal:** Archive Electron build authority and establish Windows-first CI/release governance
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

Wave 1 doc/governance alignment was already present in the working tree, but the active desktop authority still carried stale Electron metadata in `desktop/package.json` and there were no GitHub Actions workflows for the validated Windows release-gate commands.

This lane was constrained to Wave 2 only:

- archive/remove the stale Electron lane from active build authority
- add Windows-first PR and nightly/release governance
- add reproducible toolchain/build-manifest guidance
- avoid `LYRA_DATA_ROOT`, metadata/provider, and product-depth work

---

## Work Done

Bullet list of completed work:

- [x] Removed tracked Electron build authority from `desktop/package.json` and deleted the tracked Electron entrypoints.
- [x] Added a small desktop archive note (`desktop/archive/electron.md`) so the lane is intentionally retired rather than silently disappearing.
- [x] Added explicit toolchain authority via `.python-version`, `.node-version`, and `rust-toolchain.toml`.
- [x] Added Windows PR governance in `.github/workflows/windows-pr.yml`.
- [x] Added Windows nightly/release governance in `.github/workflows/windows-release-governance.yml`.
- [x] Added `scripts/write_build_manifest.ps1` and generated `.lyra-build/manifests/windows-release-gate.json`.
- [x] Fixed the renderer CI surface so the PR workflow uses `npm run test:ci` instead of hanging in watch mode.
- [x] Updated roadmap/state/worklist/registry plus the build-release brief to reflect the verified Wave 2 state.

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | local changes only (no commit yet) |

---

## Key Files Changed

- `desktop/package.json` - removed Electron builder metadata and left a Tauri-only wrapper surface.
- `.github/workflows/windows-pr.yml` - added the Windows PR gate order: backend tests, renderer tests, renderer build, docs check.
- `.github/workflows/windows-release-governance.yml` - added the Windows nightly/release order: packaged runtime build, Tauri debug build, installed-layout validation, packaged-host smoke, build manifest.
- `scripts/write_build_manifest.ps1` - emits a JSON manifest with pinned toolchain values and Windows artifact hashes.
- `docs/ROADMAP_ENGINE_TO_ENTITY.md` - moved Wave 2 out of the open-gap list and marked it locally landed.
- `docs/PROJECT_STATE.md` - recorded Tauri-only authority, workflow/toolchain truth, and local validation evidence.
- `docs/WORKLIST.md` - advanced execution order to Wave 3/runtime proof work.
- `docs/MISSING_FEATURES_REGISTRY.md` - removed the active build-governance gap.

---

## Result

Wave 2 is now locally complete in the working tree.

What is now true:

- Tauri is the only tracked desktop build authority.
- Electron build metadata and tracked Electron entrypoints are no longer part of the active desktop lane.
- Windows PR and nightly/release CI governance files exist and mirror the locally validated command order.
- Toolchain authority is explicit for Python, Node, and Rust.
- Build provenance is captured in a generated JSON manifest for the packaged Windows artifacts.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (gap removed)
- [x] `docs/SESSION_INDEX.md` row updated
- [x] Tests/build validation captured

Validation executed:

- [x] `C:/MusicOracle/.venv/Scripts/python.exe -m pytest -q` -> `115 passed`
- [x] `cd desktop\renderer-app; npm run test:ci` -> `3 passed`
- [x] `cd desktop\renderer-app; npm run build`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1 -SkipLaunchCheck -SkipToolSmokeCheck`
- [x] `cd desktop\renderer-app; npm run tauri:build -- --debug`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/validate_installed_runtime.ps1 -InstalledRoot desktop\renderer-app\src-tauri\target\debug -HealthTimeoutSeconds 45`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/write_build_manifest.ps1 -OutputPath .lyra-build/manifests/windows-release-gate.json`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1`

---

## Next Action

Implement `LYRA_DATA_ROOT` without expanding into metadata/provider/product-depth work, then run blank-machine installer proof and the long-session parity/audio soak against the finalized release contract.

