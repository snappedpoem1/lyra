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

## In Progress (Current Session S-20260306-07)

- Phase A parity hardening + launcher cutover:
  - Clean-machine packaged installer validation (sidecar bundle discovery/runtime)
  - 4-hour native audio soak + restart recovery checks

## Order Of Operation (Highest Result First)

1. Parity hardening acceptance as release gate:
   - Run `scripts/parity_hardening_acceptance.ps1`
   - Confirm canonical player/SSE + forced-restart recovery + stability soak
2. Clean-machine installer validation:
   - Verify packaged Tauri + bundled `lyra_backend.exe` discovery/startup on fresh host
3. 4-hour gaming/listening soak:
   - Confirm no crashes/dropouts; tray/media keys responsive; no queue drift
4. Oracle action UX depth:
   - Add explicit chaos intensity preset controls and richer action outcome messaging
5. Discovery quality iteration:
   - Improve Spotify-history-to-local fuzzy matching and re-check recommendation precision

## Next Up

1. Run `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild`.
2. Validate packaged sidecar on clean machine installer.
3. Run 4-hour listening/gaming soak on native backend audio path.
4. Expand Oracle action controls to include explicit chaos intensity presets in UI.
5. Improve Spotify-history-to-local-track fuzzy matching quality.
