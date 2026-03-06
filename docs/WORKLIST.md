# Worklist

Last updated: March 6, 2026

This file tracks active execution work only.

## Completed Recently

- Tauri host path made default desktop runtime path.
- Canonical backend player domain implemented (`oracle/player/*`).
- `/api/player/*` contract and `/ws/player` SSE stream implemented.
- Unified modular workspace shell made active runtime.
- Tray/media controls routed to backend player commands.
- Backend player tests and API contract tests added.
- Native playback engine abstraction wired with `miniaudio` and fallback path.
- Engine-to-Entity roadmap merged and promoted as primary forward plan.
- Docs QA script added (`scripts/check_docs_state.ps1`) and passing.
- Sidecar build script added (`scripts/build_backend_sidecar.ps1`) and validated.
- Tauri debug bundle build validated with sidecar build integrated.
- Oracle action execution expanded from stubs to live routing for vibe/playlust/chaos queue actions.
- Unified workspace oracle queue button now routes queue mutations through `/api/oracle/action/execute`.
- Unified workspace now includes Semantic Search and Deep Cut discovery panels with queue integration.
- Unified now-playing panel now renders 10-dimension profile + cached lyrics context from dossier payload.
- Unified queue sidebar now includes artist context surface (bio/genres/origin) from shrine data.
- Oracle panel now exposes explicit `start_vibe` and `start_playlust` launchers.
- Unified launcher added: `scripts/start_lyra_unified.ps1` (backend + frontend, no Docker auto-start).
- Deprecated launcher path `scripts/dev_desktop.ps1` now delegates to unified launcher.
- Backend health/status now includes acquisition bootstrap snapshot (tier availability, non-blocking).
- Unified UI now surfaces acquisition tier readiness/degraded state from backend status.
- Recommendation broker API added (`/api/recommendations/oracle`) with provider provenance, weighting, novelty bands, and acquisition leads.
- Unified Oracle surface now includes a Control Deck with provider weights, chaos presets, and broker status telemetry.
- Oracle recommendations now reveal explainable brokered picks instead of only fixed radio-mode previews.
- Legacy Docker/external-service bootstrap is now opt-in only; core app path no longer attempts to auto-start that layer.
- Bundled runtime-tool lookup added for `streamrip` and `spotdl`, establishing the packaging path away from host-global installs.
- Bundled acquisition-runtime build pipeline added:
  - `scripts/build_runtime_tools.ps1` builds standalone `spotdl.exe` and `rip.exe`
  - `scripts/build_packaged_runtime.ps1` stages those tools plus `ffmpeg`/`ffprobe` and the backend sidecar
  - packaged startup now prepends bundled runtime bins to backend PATH
- Codex helper install script added: `scripts/install_codex_helpers.ps1` (SQLite MCP + Playwright MCP for future sessions).
- Recommendation feedback loop added:
  - `POST /api/recommendations/oracle/feedback` persists accept/queue/skip/replay/acquire-request signals
  - broker ranking now applies lightweight feedback bias from recent outcomes
  - Oracle recommendation rows now emit explicit keep/queue/play/skip actions
- Acquisition radar is now actionable:
  - new oracle action `request_acquisition` writes broker leads into `acquisition_queue`
  - Oracle acquisition leads now expose one-click `Acquire` and `Dismiss` actions
- Tauri packaging artifacts now stage under dedicated build output:
  - generated `lyra_backend.exe` now builds to `.lyra-build/bin`
  - bundled runtime helpers now stage to `.lyra-build/bin/runtime/bin`
  - Tauri bundle resources now consume `.lyra-build/bin` instead of `src-tauri/bin`
- Renderer UI foundation now has a real component system:
  - Mantine provider/theme added for buttons, segmented controls, inputs, sliders, badges, and number fields
  - active unified workspace controls moved off pure hand-rolled primitives onto the new component foundation
  - Figma shell-base artifact created for Lyra workspace structure and future design iteration
- Secondary UI surfaces now follow the same foundation:
  - settings route moved onto Mantine-backed cards, text inputs, checkboxes, segmented controls, and badges
  - track dossier now opens in a Mantine drawer instead of a custom overlay shell
  - developer HUD and right-rail tabs/details now use the new component language
  - companion shell layer now exists with orb / 8-bit face modes and settings-backed toggles
- Clean-machine installer proof validated:
  - `scripts/validate_clean_machine_install.ps1` passes all artifact presence + Tauri config + binary smoke checks
  - all bundled artifacts confirmed: `lyra_backend.exe`, `rip.exe`, `spotdl.exe`, `ffmpeg.exe`, `ffprobe.exe`
- Debug packaged-host boot proof validated:
  - `scripts/packaged_host_smoke.ps1` now passes and auto-tears down after confirming packaged backend health
  - `scripts/start_lyra_unified.ps1 -Mode packaged` now writes host/backend boot logs for packaged diagnostics
- Packaged streamrip proof validated (static):
  - `scripts/validate_packaged_streamrip.ps1` passes binary presence, `--version`, `is_available()`, and command syntax
  - `oracle/acquirers/streamrip.py` default command fixed to use streamrip 2.x syntax: `rip -f <dir> search <source> track <query> --first`
  - both proof scripts wired as pre-flight steps in `scripts/parity_hardening_acceptance.ps1`
- Parity hardening acceptance now passes with packaged pre-flight enabled:
  - `scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 10 -StartupTimeoutSeconds 60`
  - includes installer proof, packaged streamrip proof, forced restart recovery, SSE validation, and short stability soak
## In Progress (Current Session S-20260306-12)

- Completed: clean-machine installer proof, debug packaged-host boot proof, packaged streamrip proof (static validation), and parity-hardening acceptance with packaged pre-flight enabled

## Order Of Operation (Highest Result First)

1. Live Qobuz acquisition proof:
   - Run `scripts/validate_packaged_streamrip.ps1 -LiveAcquire` with Qobuz credentials configured
   - Confirms G-034 fully closed: one successful packaged tier-2 acquisition
2. Parity hardening acceptance as release gate:
   - Extend from the passing short acceptance run to a 4-hour soak
   - Confirm canonical player/SSE + forced-restart recovery + long-session stability
3. 4-hour gaming/listening soak:
   - Confirm no crashes/dropouts; tray/media keys responsive; no queue drift
4. Blank-machine installer validation:
   - Install the generated setup on a clean Windows VM or second machine
   - Confirm first launch works with bundled sidecar/runtime tools only

## Next Up

1. Run `powershell -ExecutionPolicy Bypass -File scripts/validate_packaged_streamrip.ps1 -LiveAcquire` (requires Qobuz `.env` creds).
2. Run `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild` as a 4-hour soak.
3. Validate one successful live packaged/runtime-backed streamrip acquisition.
4. Run a blank-machine installer install-and-launch proof on a clean Windows VM.
5. Extend the Mantine foundation across remaining legacy routes and system panels where useful.
6. Continue graph/credits/structure depth passes after release-gate proof.
