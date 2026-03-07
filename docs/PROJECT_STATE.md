# Lyra Oracle Project State

Last audited: March 7, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: docs-only reconciliation updates pending for `S-20260307-20`
- Latest committed baseline before this audit: `a34b6fb` (`S-20260307-18` Wave 14 saved playlist UI surface)
- Program state:
  - the governance-first split modernization sequence is aligned through Wave 2
  - Wave 3 (`LYRA_DATA_ROOT` and mutable-data authority) is locally closed through the runtime contract plus explicit migrate-now/defer actions
  - Wave 4 desktop stack modernization is locally landed through the Tauri 2 host/runtime upgrade and acceptance pass
  - Wave 5 (Provider Contract and Recommendation Core) is locally landed
  - Wave 6 (Product Explainability Surfaces) is locally landed
  - Wave 7 (Release-Gate Closure) is locally landed in dev-validation mode; blank-machine proof remains blocked-external and the 4-hour soak remains deferred
  - Wave 8 (Ingest Confidence + Normalization) is locally landed
  - Wave 9 (Scout + Community Weather) is locally landed
  - Wave 10 (MBID Identity Spine) is locally landed
  - Wave 11 (Companion Pulse) is locally landed
  - Wave 12 (Oracle Action Breadth) is locally landed
  - Wave 13 (Playlist Intelligence) is locally landed
  - Wave 14 (Saved Playlist UI) is locally landed
  - `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` is landed as a docs-only UI structure authority for future route and shell work
  - `docs/PHASE_EXECUTION_COMPANION.md` remains the execution-grade phase sequence companion
- Governance state:
  - root `AGENTS.md` plus scoped lane briefs and nearest-directory `AGENTS.md` files exist
  - `docs/agent_briefs/tandem-wave-protocol.md` defines the standing two-agent split protocol
  - Tauri is the only active desktop build authority
  - Windows-first CI/release governance is defined in:
    - `.github/workflows/windows-pr.yml`
    - `.github/workflows/windows-release-governance.yml`

## 2) Architecture State

- Backend:
  - Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry default: `LYRA_DATA_ROOT\db\lyra_registry.db`
  - Chroma storage default: `LYRA_DATA_ROOT\chroma\`
- Desktop runtime:
  - Tauri 2 host in `desktop/renderer-app/src-tauri/`
  - React/Vite renderer in `desktop/renderer-app/`
  - Mantine remains infrastructure; the main user-facing routes are progressively restyled into a bespoke shell language
  - `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` is the structural authority for route archetypes, shell-region responsibilities, semantic UI blocks, and explainability placement
  - Playlists now expose first-class saved-playlist creation and browsing through the active route surface
- Playback authority:
  - canonical backend player domain in `oracle/player/*`
  - persisted `player_state` and `player_queue` tables
  - API surface: `/api/player/*`
  - SSE stream: `/ws/player`
- Oracle and recommendation state:
  - recommendation broker contract is exposed through `POST /api/recommendations/oracle`, `POST /api/recommendations/oracle/feedback`, and `GET /api/recommendations/providers/health`
  - broker fuses local radio, Last.fm similar-track signals, ListenBrainz community top-recording signals, Scout cross-genre bridge leads, and ListenBrainz community weather signals
  - provider health registry and degraded-state reporting are live
- Acquisition and runtime packaging:
  - `LYRA_DATA_ROOT` is the config-owned writable-data authority
  - `.lyra-build` remains build/runtime artifact staging only
  - explicit migration flow exists in both CLI and runtime API
  - packaged proof and validation scripts are active:
    - `scripts/validate_clean_machine_install.ps1`
    - `scripts/validate_packaged_streamrip.ps1`
    - `scripts/packaged_host_smoke.ps1`
    - `scripts/validate_installed_runtime.ps1`
    - `scripts/parity_hardening_acceptance.ps1`
- Frozen-runtime hardening:
  - frozen `PROJECT_ROOT` resolves from `sys.executable`
  - generated cache/log/tmp/runtime-state roots resolve from config-owned paths
  - sidecar packaging includes the broader Flask blueprint surface

## 3) Runtime Metrics

From `.venv\Scripts\python.exe -m oracle.status` on this workstation after the Wave 7 and later follow-up passes:

- the dev data root at `%LOCALAPPDATA%\Lyra\dev` is now the active migrated library root
- the full library data is present under the active data root, so `LYRA_USE_LEGACY_DATA_ROOT` is no longer required for normal dev validation
- the legacy repo-root layout remains compatibility-only state rather than the silent default

## 4) Verification Results (Current High-Water Marks)

- `.venv\Scripts\python.exe -m pytest -q` -> success (`241 passed`) after Wave 13
- `cd desktop\renderer-app; npx vitest run` -> success (`34 passed`) after Wave 14
- `cd desktop\renderer-app; npm run build` -> success after Wave 14
- `cd desktop\renderer-app; npx tsc --noEmit` -> success after Wave 6 frontend plumbing
- `powershell -ExecutionPolicy Bypass -File scripts/validate_clean_machine_install.ps1` -> success (local artifact/layout proof)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_packaged_streamrip.ps1 -LiveAcquire` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/validate_installed_runtime.ps1 -InstalledRoot desktop\renderer-app\src-tauri\target\debug -HealthTimeoutSeconds 45` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SkipInstallerProof -UseLegacyDataRoot -SoakSeconds 60 -StartupTimeoutSeconds 90` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success

## 5) Documentation Truth Status

- Tracked markdown files: 112 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Execution companion: `docs/PHASE_EXECUTION_COMPANION.md`
- Session ledger: `docs/SESSION_INDEX.md`
- Current governance wave:
  - Waves 1 through 14 are now represented as locally landed or explicitly release-gated
  - a standing tandem-wave protocol defines how Codex and Copilot split future waves without overlapping file ownership
  - the execution companion remains the iteration-level reference while the roadmap stays forward-plan authority

## 6) Active Gaps

1. Blank-machine installer install-and-launch validation is still pending outside this workstation and is blocked by the lack of a clean Windows machine or VM.
2. Native audio (`miniaudio`) full 4-hour production soak is intentionally deferred until a later release-gate window; bounded parity runs pass in dev-validation mode.
3. `SPEC-009` adoption is not complete across every remaining route or panel.
4. Wave 8 ingest confidence rows are written for new lifecycle events going forward; startup backfill covers existing placed tracks, but historical normalized/enriched states are not reconstructed.

## 7) Immediate Next Pass

1. Continue `oracle mbid resolve` passes until recording MBID coverage clears the practical threshold for broad credit enrichment, then run `oracle credits enrich --limit 500`.
2. Scope Wave 15 as the next implementation wave: structure analysis coverage hardening, similarity graph growth, or acquisition waterfall improvements.
3. Run blank-machine installer install-and-launch proof once a clean Windows machine or VM is available.
4. Run full 4-hour parity/audio soak when the release-gate lane is reopened.
