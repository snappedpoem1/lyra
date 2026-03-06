# Session Log - S-20260306-12

**Date:** 2026-03-06
**Goal:** Advance packaged-installer and runtime-backed acquisition proof, prepare delegation brief, validate, commit, and push
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

Packaged-runtime work had reached static artifact staging and bundled helper generation, but the release gate was still open on three fronts:

- repeatable clean-machine installer proof
- repeatable packaged streamrip proof
- an honest packaged-host smoke path that validated host + bundled backend boot instead of hanging or probing the wrong runtime state

The session goal was to close as much of that gate as possible, document a parallel-agent brief for external validation, and leave only true off-box or credential-gated work behind.

---

## Work Done

Bullet list of completed work:

- Added `scripts/validate_clean_machine_install.ps1` to verify packaged artifact presence, Tauri resource configuration, and bundled executable smoke checks.
- Added `scripts/validate_packaged_streamrip.ps1` to validate bundled `rip.exe` presence, bundled resolution via `oracle.acquirers.streamrip`, and streamrip 2.x command generation.
- Added `docs/agent_briefs/release-gate-parallel-brief.md` so a second agent can execute clean-machine installer proof and live packaged acquisition proof in parallel.
- Added `scripts/packaged_host_smoke.ps1` and fixed its lifecycle so it proves packaged-host readiness, captures the host pid, and auto-tears down unless explicitly told to keep running.
- Fixed `desktop/renderer-app/src-tauri/tauri.conf.json` bundled resource path so Tauri consumes repo-root `.lyra-build/bin`.
- Relaxed `desktop/renderer-app/package.json` packaged prebuild path to skip launch/tool smoke during bundle assembly and keep those checks in explicit validation scripts instead.
- Hardened `scripts/start_lyra_unified.ps1` packaged mode with packaged-host env wiring, boot-log paths, and better packaged failure diagnostics.
- Hardened `desktop/renderer-app/src-tauri/src/main.rs` with packaged host boot logging so host/backend launch failures are inspectable from disk.
- Hardened `scripts/build_backend_sidecar.ps1` to build in a unique temp dist and then stage the final sidecar artifact, avoiding direct PyInstaller writes into `.lyra-build/bin`.
- Added packaged-backend runtime logging in `lyra_api.py` so frozen-sidecar route/bootstrap issues can be diagnosed from `logs/packaged-backend.log`.
- Confirmed local packaged launch now reaches healthy backend state and that parity-hardening acceptance passes with packaged pre-flight enabled.

---

## Commits

| SHA (short) | Message |
|---|---|
| `2437dc0` | `[S-20260306-12] feat: harden packaged release-gate proofs` |
| `fe92728` | `[S-20260306-12] docs: record packaged release-gate state` |

---

## Key Files Changed

- `scripts/validate_clean_machine_install.ps1` - added repeatable clean-machine artifact and bundled-executable proof
- `scripts/validate_packaged_streamrip.ps1` - added repeatable bundled streamrip proof and optional live-acquire path
- `scripts/packaged_host_smoke.ps1` - added packaged-host readiness smoke and automatic teardown
- `scripts/start_lyra_unified.ps1` - packaged-mode env wiring, boot-log reporting, and healthier packaged diagnostics
- `scripts/build_backend_sidecar.ps1` - unique temp dist build plus staged final sidecar copy
- `desktop/renderer-app/src-tauri/src/main.rs` - host boot logging for packaged diagnostics
- `lyra_api.py` - packaged backend file logging for frozen/runtime diagnosis
- `desktop/renderer-app/src-tauri/tauri.conf.json` - fixed bundled resource path
- `desktop/renderer-app/package.json` - moved packaged prebuild smoke concerns out of `tauri:build`
- `docs/PROJECT_STATE.md` - recorded packaged proof, packaged smoke, and current next gate

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Yes. Lyra now has:

- a passing clean-machine artifact proof
- a passing packaged streamrip static proof
- a passing local debug packaged-host boot proof
- a passing parity-hardening acceptance run with the packaged proofs enabled as pre-flight

The remaining release-gate work is now clearly external or credential-gated:

- blank-machine install-and-launch validation
- live packaged/runtime-backed streamrip acquisition
- long-session native-audio soak

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## G-035 Installer Hardening Addendum (S-20260306-12 continuation 2)

Work done while Codex handles parallel tasks:

**`lyra_api.py` — frozen `PROJECT_ROOT` fix**
- Changed `Path.cwd()` to `Path(sys.executable).parent` when `sys.frozen` is True
- Sidecar now anchors its root paths to its own location regardless of the working directory set by the host

**`oracle/api/app.py` — HuggingFace cache path frozen fix**
- `hf_home` was derived from `Path(__file__).resolve().parent.parent.parent` which, in a PyInstaller frozen binary, resolves into the `_MEIPASS` temp directory
- Fixed to use `oracle.config.PROJECT_ROOT` which correctly resolves to the sidecar's install location

**`scripts/build_backend_sidecar.ps1` — expanded submodule collection**
- Added `--collect-submodules` for: `oracle.player`, `oracle.acquirers`, `oracle.db`, `oracle.integrations`, `oracle.embedders`, `oracle.importers`, `oracle.enrichers`
- Previously only `oracle.api.blueprints` was collected; dynamic imports in other subpackages would fail on a clean machine

**`desktop/renderer-app/src-tauri/tauri.conf.json` — Windows installer metadata**
- Added `shortDescription`, `longDescription`, `copyright`
- Added `windows.nsis` block: `installMode: currentUser`, `languages: ["English"]`
- Added `windows.wix` block: `language: en-US`

**`scripts/validate_clean_machine_install.ps1` — simulated install layout check**
- New section creates a temp directory mimicking the Tauri installed tree: `<install>/resources/lyra_backend.exe` + `<install>/resources/runtime/bin/rip.exe`
- Verifies that `resolve_packaged_runtime_anchor` logic (as implemented in main.rs) would chain sidecar → `resources/` → `resources/runtime/bin` correctly
- All 4 new assertions pass

**Validation:** `validate_clean_machine_install.ps1` → all checks pass (including new section); `pytest -q` → 99 passed; `check_docs_state.ps1` → OK

Command run:
```
powershell -ExecutionPolicy Bypass -File scripts\validate_packaged_streamrip.ps1 -LiveAcquire
```

Result: **PASS — all 6 checks passed**

- rip.exe path: `C:\MusicOracle\runtime\bin\rip.exe` (35 MB, version 2.1.0)
- Artist/track tested: Burial — Archangel
- Downloaded file: `C:\Users\Admin\AppData\Local\Temp\lyra_streamrip_proof_u63t6zqk\02. Burial - Archangel.flac`
- Source: streamrip (Qobuz)
- Error: None

**G-034 fully closed.**

Docs updated:
- `docs/MISSING_FEATURES_REGISTRY.md` — G-034 moved to `live`
- `docs/PROJECT_STATE.md` — live acquisition proof run added to validated commands
- `docs/WORKLIST.md` — live acquisition task marked done; Next Up updated
- `docs/SESSION_INDEX.md` — S-20260306-12 result updated

---

## Next Action

What is the single most important thing to do next?

Run `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild` as a 4-hour soak, then execute blank-machine installer install-and-launch proof on a clean Windows VM.
