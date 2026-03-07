# Worklist

Last updated: March 7, 2026

This file tracks active execution work only.

## Completed Recently

- Added a docs-only UI structure system for future frontend work:
  - `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` now defines route inventory, shell responsibilities, canonical page archetypes, semantic UI blocks, and phased frontend adoption rules
  - `docs/agent_briefs/frontend-provenance-brief.md` now points future UI explainability work at `SPEC-009` in addition to `SPEC-005`
- Added the execution-grade phase companion for the remaining program:
  - `docs/PHASE_EXECUTION_COMPANION.md` now defines iteration order, owner splits, validation, and handoff rules for Waves 3 through 11
  - `docs/ROADMAP_ENGINE_TO_ENTITY.md` remains the forward-plan authority while the companion carries execution sequencing
- Standing tandem execution protocol landed for future shared waves:
  - `docs/agent_briefs/tandem-wave-protocol.md` defines wave owner vs parallel lane owner, file-claim rules, sync windows, and per-wave split patterns
  - root `AGENTS.md` and `.github/copilot-instructions.md` now point both agents at the same shared-wave protocol
- Wave 2 build/release governance landed locally:
  - stale Electron build authority removed from tracked desktop files
  - `desktop/package.json` is now a Tauri-only wrapper
  - Windows PR workflow now runs backend pytest, renderer `test:ci`, renderer build, and docs QA
  - Windows nightly/release workflow now runs packaged runtime build, Tauri debug build, installed-layout validation, packaged-host smoke, and build-manifest emission
  - toolchain authority now lives in `.python-version`, `.node-version`, and `rust-toolchain.toml`
  - build provenance now emits `.lyra-build/manifests/windows-release-gate.json`
- Tauri host path made the default desktop runtime path.
- Canonical backend player domain is implemented (`oracle/player/*`).
- `/api/player/*` contract and `/ws/player` SSE stream are implemented.
- Unified modular workspace shell is the active runtime.
- Tray and media controls route to backend player commands.
- Native playback engine abstraction is wired with `miniaudio` and fallback behavior.
- Recommendation broker API is live with provider provenance, weighting, novelty bands, acquisition leads, and persisted feedback.
- Oracle acquisition radar is actionable through `request_acquisition`.
- Docker and legacy external-service bootstrap are no longer part of the default app path.
- Bundled runtime-tool lookup exists for `streamrip` and `spotdl`.
- Bundled acquisition-runtime build pipeline exists:
  - `scripts/build_runtime_tools.ps1`
  - `scripts/build_packaged_runtime.ps1`
- Tauri packaging artifacts stage under `.lyra-build/bin` and `.lyra-build/bin/runtime/bin`.
- Mantine-based UI foundation is active across the main shell and key secondary surfaces.
- Clean-machine artifact proof is validated:
  - `scripts/validate_clean_machine_install.ps1` passes
  - bundled artifacts confirmed: `lyra_backend.exe`, `rip.exe`, `spotdl.exe`, `ffmpeg.exe`, `ffprobe.exe`
- Debug packaged-host boot proof is validated:
  - `scripts/packaged_host_smoke.ps1` passes and auto-tears down
  - packaged host boot logs are written for diagnostics
- Installed-layout validation is now available and locally proven:
  - `scripts/validate_installed_runtime.ps1` validates installed or installed-style app roots
  - rebuilt `target\debug` host passes installed-layout launch smoke with sidecar/runtime assets under `resources\`
- Packaged runtime-root resolution is hardened for installed layouts in the Tauri host.
- Frozen-runtime hardening landed:
  - frozen `PROJECT_ROOT` uses `Path(sys.executable).parent`
  - HuggingFace cache roots resolve from `oracle.config.PROJECT_ROOT`
  - sidecar build collects broader Oracle subpackages for clean-machine frozen installs
- Frozen sidecar completeness is now corrected:
  - `scripts/build_backend_sidecar.ps1` explicitly hidden-imports `oracle.api.blueprints.*`
  - sidecar launch check now proves the bundled backend exposes the real API contract
- Live packaged streamrip acquisition proof is validated:
  - `scripts/validate_packaged_streamrip.ps1 -LiveAcquire` passed
  - G-034 is closed
- Spotify import background endpoints are live:
  - `POST /api/spotify/import`
  - `GET /api/spotify/import/status`
  - backend suite is now `106 passed`
- Packaged proof scripts are now deterministic:
  - `scripts/packaged_host_smoke.ps1` stops any existing backend listener before launch
  - `scripts/parity_hardening_acceptance.ps1` records log/JSONL artifacts and runs transport mutations during soak
- Safe parallel lane progressed while soak/runtime hardening continued elsewhere:
  - Mantine controls landed for Search, Oracle, and Artist surfaces
  - acquisition queue prioritization now works again against `priority_score`
  - ListenBrainz discovery added 136 queue candidates
  - bounded structure analysis increased `track_structure` coverage (`159 -> 172`)
  - tiny queue drain produced 1 successful streamrip ingest and 1 retried failure
- Tier 1 Qobuz runtime path is fixed again:
  - `oracle/acquirers/qobuz.py` no longer references undefined `QOBUZ_SERVICE_URL`
  - second tiny drain proved T1 success (`Bear Hands - Agora`)
  - duplicate-aware queue handling now resolves the exact downloaded row immediately
  - true duplicate hits can complete without waiting for stale-row reconciliation
  - mismatch cases like `Agora -> 2AM` now re-queue immediately with an explicit mismatch error instead of stale downloaded drift
  - backend suite is now `109 passed`
- Bespoke shell cleanup advanced on the renderer:
  - Home was rebuilt into a calmer studio-deck layout
  - Queue and Playlists now use matching bespoke hero treatments instead of the older flat panel stack
  - Mantine remains the infrastructure layer, not the visible design authority
- Runtime/source separation advanced without touching the release-gate lanes:
  - frozen `oracle.config` now matches `lyra_api.py` by resolving packaged `PROJECT_ROOT` from `sys.executable`
  - generated logs, temp scratch, runtime state, and default CLAP cache now route through `.lyra-build/*` config roots
  - runtime state keeps legacy repo-root read compatibility while new writes move behind `.lyra-build/state`
  - backend suite is now `114 passed`
- Bespoke shell cleanup continued safely while the soak lane stayed separate:
  - Oracle now uses a fuller observatory-style hero and control deck framing
  - Vibe Library now uses the same bespoke shell language instead of the older flat panel stack
  - Oracle recommendations now refetch correctly when the current seed track changes
  - renderer tests/build passed again after the route pass
- Notes-driven shell cleanup continued in another safe lane:
  - Library now has a proper archive hero and current-slice framing instead of only a minimal intro
  - playlist detail now reads like a first-class thread surface instead of a leftover detail page
  - renderer tests/build passed again after the Library + playlist-detail route pass
- Notes-driven system panel cleanup also landed in the same safe lane:
  - Backend and Doctor panels now use the same summary-first bespoke shell language
  - settings diagnostics no longer read like older flat inspector blocks
  - renderer tests/build and backend pytest stayed green after the panel pass
- Wave 4 renderer parallel lane prep landed (S-20260307-03) while Codex runs Wave 3:
  - `agentActionRouter.ts` hardcoded `http://localhost:5000` replaced with `resolveApiUrl()` — API base is now configurable
  - `tauriHost.ts` runtime detection extended to cover both Tauri v1 (`__TAURI_IPC__`) and v2 (`__TAURI_INTERNALS__`)
  - safe in-range renderer dep bumps: `@tabler/icons-react` 3.40.0, `framer-motion` 12.35.1, `@tanstack/react-router` 1.166.2
  - `jsdom` added as devDependency for per-file Vitest browser environment
  - renderer test suite grew from 3 to 26 tests (agentActionRouter: 18 tests, tauriHost: 5 tests)
  - renderer `test:ci` and `build` both pass clean

- Wave 3 runtime/data-root contract landed (S-20260307-02):
   - `oracle.config` now exposes authoritative `LYRA_DATA_ROOT` resolution with `%LOCALAPPDATA%\Lyra\dev` for dev and `%LOCALAPPDATA%\Lyra` for frozen installs
   - runtime-owned mutable paths now derive from that root while `.lyra-build` stays build-only
   - backend startup, worker, doctor, runtime-state, ingest watcher, Chroma users, CLI defaults, and packaged-host startup now follow the contract
   - legacy repo-root mutable data is explicitly detected and can only be reused via `LYRA_USE_LEGACY_DATA_ROOT=1`
   - strict validator plus backend suite now pass (`scripts/validate_data_root_contract.ps1`, `.venv\Scripts\python.exe -m pytest -q` => `119 passed`)
- Wave 3 closeout landed locally (S-20260307-04):
   - explicit migrate-now/defer flow is now actionable through both CLI and runtime API
   - `oracle.data_root_migration` now reports action state plus API affordances for migration-aware consumers
   - core API now exposes `GET /api/runtime/data-root`, `POST /api/runtime/data-root/migrate`, and `POST /api/runtime/data-root/defer`
   - isolated API coverage was added for the new migration contract
- Wave 4 desktop stack modernization landed locally (S-20260307-03 + S-20260307-05):
   - renderer prep landed first: API base resolution, Tauri v1/v2 runtime detection, safe dep bumps, and 26 renderer tests
   - host/runtime contract is now on Tauri 2 (`@tauri-apps/api` 2.x, `@tauri-apps/cli` 2.x, `tauri` 2.x, `tauri-build` 2.x)
   - tray behavior was migrated onto the Tauri 2 tray API and the global-shortcut plugin
   - Tauri config moved to schema `2` and the main desktop capability file now exists under `src-tauri/capabilities/default.json`
   - Wave 4 acceptance passed locally: renderer `test:ci`, renderer `build`, Tauri debug build, and packaged-host smoke

## In Progress (Current Session S-20260306-29)

- Active: docs synchronization and tandem-wave protocol hardening after local Wave 2 landing

- Wave 5 provider contract and recommendation core landed locally (S-20260307-07):
   - all providers return normalized `ProviderResult` with structured evidence (`SPEC-004`)
   - broker output is versioned with `schema_version`, per-provider `provider_reports`, `degraded` flag, and `degradation_summary`
   - provider health registry tracks success/degraded/unavailable transitions with structured logging (`SPEC-006`)
   - provider health exposed in `/api/health`, `/api/status`, `/api/recommendations/providers/health`, and `oracle doctor`
   - backend suite is now `153 passed`
- Wave 6 product explainability surfaces landed locally (S-20260307-07):
   - frontend Oracle route uses brokered recommendation path (`SPEC-005`)
   - provider chips, confidence bands, degraded-state banners, and expandable "Why this?" evidence trace active
   - TypeScript types and Zod schemas for SPEC-004 payload in place
   - renderer zero type errors and build pass clean
- Frozen sidecar rebuilt post-Wave 5+6 (S-20260307-07):
   - `scripts/build_backend_sidecar.ps1` rebuilt `.lyra-build/bin/lyra_backend.exe` (310.7 MB, March 7 2026 15:10)
   - sidecar launch check passed after rebuild
- Wave 7 parity soak validated (S-20260307-07):
   - `scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SkipInstallerProof -UseLegacyDataRoot -SoakSeconds 60 -StartupTimeoutSeconds 90` passed
   - Step 1+2 smoke (health, library, canonical player commands, SSE stream) passed
   - restart recovery passed
   - 60-second stability soak with pause/resume and seek mutations passed
   - constraint: `LYRA_USE_LEGACY_DATA_ROOT=1` needed because dev data root has not been migrated with library data; `-UseLegacyDataRoot` flag added to parity script for this workaround
   - `scripts/parity_hardening_acceptance.ps1` extended with `-UseLegacyDataRoot` switch

## In Progress (Current Session S-20260307-12)

- Active: Wave 11 (Companion Pulse) — completed: SPEC-011, `oracle/companion/pulse.py` (`CompanionPulse` + `get_companion_pulse` singleton), `/ws/companion` SSE blueprint, blueprint registered in registry, 14 new tests (215 total passing), `useCompanionStream.ts` SSE hook, `companionLines.ts` authored templates, `LyraCompanion.tsx` now event-driven (stream consumer with static fallback), `settingsStore.ts` `notificationsEnabled` added. Renderer: 26 tests passing, clean build.
- Active: Wave 12 (Oracle Action Breadth) — **completed S-20260307-14**: `PlayerService.set_volume()` + `clear_queue()`; `/api/player/volume` + `/api/player/queue/clear`; 8 new oracle execute actions (`resume`, `set_volume`, `set_shuffle`, `set_repeat`, `clear_queue`, `play_artist`, `play_album`, `play_similar`); agentActionRouter 8 new cases; 11 new contract tests; 226 Python tests passing; clean npm build; G-037 closed.

## Next Up

1. Continue `oracle mbid resolve` passes until recording_mbid coverage exceeds 50%, then run `oracle credits enrich --limit 500` for MBID-backed credit rows.
2. **Wave 13**: scope candidates — playlist intelligence (save/load/edit playlists), acquisition waterfall improvements, native OS notification delivery (Tauri plugin), or deeper intelligence surfaces.
3. Resume blank-machine installer proof once a clean Windows machine or VM is available.
4. Run full 4-hour parity soak when the release-gate lane is reopened.

- Active: Wave 8 (Ingest Confidence + Normalization) — completed: SPEC-007, `oracle/ingest_confidence.py`, DB table, 5-stage `_native_ingest` hook, `/api/ingest/confidence/*` endpoints, `_check_ingest_confidence` in doctor, startup backfill, 14 new tests, full suite 167 passing

## In Progress (Current Session S-20260307-07)

- Active: Wave 7 doc sync — recording Wave 5+6 completion state and Wave 7 blocked items with evidence

## In Progress (Current Session S-20260307-05)

- Active: Wave 4 closeout sync and Wave 5 handoff after the local Tauri 2 host migration

## Order Of Operation (Highest Result First)

1. Metadata/recommendation/provider expansion:
   - deepen provider contracts, provenance, and source integration
2. Blank-machine installer proof:
  - blocked-external until a clean Windows machine or VM exists
3. Final parity/audio soak closure:
  - deferred until a later release-gate window
4. UI provenance and Oracle depth:
   - surface rationale, degraded states, and recommendation evidence where it matters
5. Post-release trust and ritual depth:
   - execute ingest-confidence, Scout/community-weather, MBID/live-orbit, and companion/native-ritual waves only after the earlier gates close

## Next Up

1. Open Wave 10 (MBID Identity Spine + Live Orbit): write spec first, then implement per `docs/PHASE_EXECUTION_COMPANION.md`.
2. Resume blank-machine installer proof once a clean Windows machine or VM is available.
3. Run full 4-hour parity soak when the release-gate lane is reopened.
4. Use `docs/PHASE_EXECUTION_COMPANION.md` as the iteration-level execution reference for any later wave opening.
5. Use `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` as the structural authority before any future cross-route frontend refactor or new explainability-surface adoption pass.
