# Lyra Oracle Project State

Last audited: March 6, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: dirty (active implementation session in progress)
- Latest committed baseline before this audit: `b2bcde4` (bundled packaged acquisition runtime tools)

## 2) Architecture State (Current)

- Backend: Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry: `lyra_registry.db`
  - Chroma storage: `chroma_storage/`
- Desktop runtime:
  - Tauri host in `desktop/renderer-app/src-tauri/`
  - React/Vite renderer in `desktop/renderer-app/`
  - Canonical launcher: `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev`
  - Packaged runtime builder: `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1`
  - Docker is not required and not auto-started in unified launch path
  - Legacy external-service bootstrap is now opt-in only via `LYRA_BOOTSTRAP_LEGACY_SERVICES=1`
  - Unified runtime shell is active (Library, Semantic, Deep Cut, Now Playing, Queue, Artist Context, Oracle)
  - Unified Oracle pane shows acquisition tier readiness/degraded status from backend `/api/status`
  - Unified Control Deck is active inside the Oracle surface:
    - novelty band controls (`safe`, `stretch`, `chaos`)
    - provider weight sliders (`local`, `lastfm`, `listenbrainz`)
    - explicit chaos intensity presets (`low`, `medium`, `high`)
    - provider readiness/status chips
  - Oracle queue action button now executes backend `/api/oracle/action/execute` routes
  - Oracle recommendation surface now uses brokered explainable picks instead of only fixed radio-mode fetches
  - Now Playing intelligence card uses dossier payload for:
    - 10-dimension track profile
    - cached lyrics/context (Genius cache payload)
- Playback authority:
  - Canonical backend player domain in `oracle/player/*`
  - Persisted `player_state` and `player_queue` tables
  - API surface: `/api/player/*`
  - `/ws/player` is SSE event stream
  - `/api/playback/record` retained as compatibility-only path
  - Acquisition bootstrap snapshot exposed in `/api/health` and `/api/status` without Docker boot
  - Runtime-service packaging policy now exposed at:
    - `GET /api/runtime/services`
  - Oracle action routing now performs concrete backend actions for:
    `queue_tracks`, `start_vibe`, `start_playlust`, `switch_chaos_intensity`, and `request_acquisition`
  - Recommendation broker contract now exposed at:
    - `POST /api/recommendations/oracle`
    - `POST /api/recommendations/oracle/feedback`
  - Broker currently fuses:
    - local radio engine (`flow`, `chaos`, `discovery`)
    - Last.fm similar-track signals when API key is configured
    - ListenBrainz community top-recording signals
  - Recommendation feedback is now persisted in SQLite and used as a lightweight ranking bias for future broker results.
  - Acquisition tooling runtime now supports bundled lookup for:
    - `streamrip` (`rip.exe` / `rip`) from `runtime/bin`, `runtime/tools`, or `runtime/acquisition-tools`
    - `spotdl` (`spotdl.exe` / `spotdl`) from the same bundled runtime locations
  - Bundled acquisition helper executables are now built and staged by:
    - `scripts/build_runtime_tools.ps1`
    - `scripts/build_packaged_runtime.ps1`
  - Generated packaged artifacts now stage under:
    - `.lyra-build/bin`
    - `.lyra-build/bin/runtime/bin`
  - Tauri packaged resources now consume:
    - `.lyra-build/bin`
  - Packaged backend startup now exports `LYRA_RUNTIME_ROOT` and prepends bundled runtime bins to backend `PATH`
  - Docker-class services are now explicitly classified as optional legacy/external layers rather than core runtime architecture
  - Broker responses include:
    - provider weights
    - provider availability/degradation messages
    - per-track provenance signals
    - acquisition leads for tracks not yet in the local library
  - Unified Oracle UI now includes forward actions on broker output:
    - recommendation actions: `Keep`, `Queue`, `Play`, `Skip`
    - acquisition lead actions: `Acquire`, `Dismiss`

## 3) Runtime Metrics

From `python -m oracle status`:

- Tracks total: 2,454
- Tracks active: 2,454
- Embeddings: 2,454
- Scored tracks: 2,454
- Vibes: 9
- Queue pending: 2,036
- Spotify history rows: 127,312
- Spotify library rows: 4,026
- Playback events: 30,680

## 4) Verification Results (This Audit)

- `python -m pytest -q` -> `96 passed`
- `cd desktop\renderer-app; npm run test` -> `1 file / 3 tests passed`
- `cd desktop\renderer-app; npm run build` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/build_backend_sidecar.ps1` -> success (`.lyra-build/bin/lyra_backend.exe`)
- `powershell -ExecutionPolicy Bypass -File scripts/build_runtime_tools.ps1` -> success (`runtime/bin/*.exe` plus staged `.lyra-build/bin/runtime/bin` helpers)
- `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1 -SkipLaunchCheck -SkipToolSmokeCheck` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/smoke_step1_step2.ps1 -StartupTimeoutSeconds 60 -SoakSeconds 20` -> success (full Step 1/2 path, including canonical player API + SSE checks)
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 10 -StartupTimeoutSeconds 60` -> success (smoke + forced restart recovery + SSE + stability soak)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 90 -LeaveRunning` -> success (cold start; backend + frontend active)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 30 -LeaveRunning` -> success (warm start; backend reused)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode packaged -SkipSidecarBuild` -> expected non-zero failure with clear error when packaged host binary is absent
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success
- `python -m oracle doctor` -> success with bundled `streamrip` and `spotdl` detected
- `python -m oracle status` -> success with healthy core metrics

## 5) Documentation Truth Status

- Tracked markdown files: 26 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Archived plan pointer: `docs/MASTER_PLAN_EXPANDED.md`

## 6) Active Gaps

1. Clean-machine packaged installer validation for bundled `lyra_backend.exe`, `streamrip`, `spotdl`, `ffmpeg`, and `ffprobe`.
2. Native audio (`miniaudio`) production soak validation across real devices/sessions.
3. Runtime/source separation policy is still partial beyond the new dedicated `.lyra-build` staging root.
4. One successful packaged/runtime-backed tier-2 streamrip acquisition proof is still pending.

## 7) Immediate Next Pass

1. Run packaged installer validation on a clean machine to confirm bundled sidecar + runtime-tool discovery.
2. Run parity-hardening acceptance (4-hour soak + pause/seek/repeat/recovery across restart).
3. Validate one successful packaged/runtime-backed streamrip acquisition.
4. Continue runtime/source separation cleanup after installer proof.
5. Continue graph/credits/structure depth passes once release-gate proof is complete.
