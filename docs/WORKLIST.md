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

## In Progress (Current Session S-20260306-08)

- Architecture unification + forward-facing utility pass:
  - Broker feedback/event logging
  - Acquisition radar one-click actions
  - Release-gate validation (packaged installer + native-audio soak)

## Order Of Operation (Highest Result First)

1. Docker elimination / packaged runtime pass:
   - Validate packaged installer on a clean machine with bundled `streamrip`, `spotdl`, `ffmpeg`, and `ffprobe`
   - Keep Docker only as optional legacy compatibility layer
2. Parity hardening acceptance as release gate:
   - Run `scripts/parity_hardening_acceptance.ps1`
   - Confirm canonical player/SSE + forced-restart recovery + stability soak
3. Recommendation feedback loop:
   - Persist accepts/skips/replays from brokered picks
   - Use feedback to rank future recommendations
4. 4-hour gaming/listening soak:
   - Confirm no crashes/dropouts; tray/media keys responsive; no queue drift
5. Acquisition radar actions:
   - Turn brokered non-library leads into one-click acquisition actions

## Next Up

1. Validate the packaged installer on a clean machine with bundled `streamrip`, `spotdl`, `ffmpeg`, and `ffprobe`.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild`.
3. Persist broker acceptance/skip/replay events and expose them in ranking.
4. Turn acquisition radar leads into one-click acquisition actions.
5. Continue runtime/source separation cleanup after installer proof.
