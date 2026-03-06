# Lyra Oracle Project State

Last audited: March 6, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: clean after session `S-20260306-12` finalization
- Latest committed baseline before this audit: `0a85175` (secondary shell surfaces docs/state stamp)

## 2) Architecture State (Current)

- Backend: Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry: `lyra_registry.db`
  - Chroma storage: `chroma_storage/`
- Desktop runtime:
  - Tauri host in `desktop/renderer-app/src-tauri/`
  - React/Vite renderer in `desktop/renderer-app/`
  - Renderer component foundation now includes Mantine (`@mantine/core`, `@mantine/hooks`) with a Lyra-specific theme layer
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
  - Unified workspace shell controls now use the new Mantine-backed foundation for:
    - mode switching via segmented controls
    - action buttons
    - text/number inputs
    - provider sliders
    - status/signal badges
  - Secondary renderer surfaces now follow the same foundation for:
    - settings route controls
    - right-rail tab switching and detail badges
    - track dossier drawer
    - developer HUD shell card
  - Oracle queue action button now executes backend `/api/oracle/action/execute` routes
  - Oracle recommendation surface now uses brokered explainable picks instead of only fixed radio-mode fetches
  - Now Playing intelligence card uses dossier payload for:
    - 10-dimension track profile
    - cached lyrics/context (Genius cache payload)
  - Figma base artifact created for shell planning:
    - Lyra Shell Foundation (FigJam)
  - Companion shell layer is now live as a settings-backed floating surface with:
    - `orb` mode
    - `pixel` mode
    - route-through to shell tuning in settings
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
  - Packaged installer proof scripts now active:
    - `scripts/validate_clean_machine_install.ps1` — verifies all bundled artifacts, Tauri resource config, and binary smoke checks
    - `scripts/validate_packaged_streamrip.ps1` — verifies bundled `rip.exe`, `is_available()` bundled resolution, and streamrip 2.x command syntax
    - `scripts/packaged_host_smoke.ps1` — verifies the debug packaged host can boot the bundled backend to healthy state and tear down cleanly
    - Both scripts are wired as pre-flight steps in `scripts/parity_hardening_acceptance.ps1`
  - `oracle/acquirers/streamrip.py` default command now uses correct streamrip 2.x syntax:
    `rip -f <output_dir> search <source> track <query> --first`
    (override via `LYRA_STREAMRIP_CMD_TEMPLATE`; source defaulted by `LYRA_STREAMRIP_SOURCE`)
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

- `python -m pytest -q` -> `99 passed`
- `cd desktop\renderer-app; npm run test` -> `1 file / 3 tests passed`
- `cd desktop\renderer-app; npm run build` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/build_backend_sidecar.ps1` -> success (`.lyra-build/bin/lyra_backend.exe`)
- `powershell -ExecutionPolicy Bypass -File scripts/build_runtime_tools.ps1` -> success (`runtime/bin/*.exe` plus staged `.lyra-build/bin/runtime/bin` helpers)
- `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1 -SkipLaunchCheck -SkipToolSmokeCheck` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/validate_clean_machine_install.ps1` -> success (all artifact presence + Tauri config + executable smoke checks)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_packaged_streamrip.ps1` -> success (binary presence + version + is_available() + command syntax)
- `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45` -> success (debug packaged host boot reaches backend healthy state and auto-tears down)
- `powershell -ExecutionPolicy Bypass -File scripts/smoke_step1_step2.ps1 -StartupTimeoutSeconds 60 -SoakSeconds 20` -> success (full Step 1/2 path, including canonical player API + SSE checks)
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 10 -StartupTimeoutSeconds 60` -> success (installer proof + packaged streamrip proof + smoke + forced restart recovery + SSE + stability soak)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 90 -LeaveRunning` -> success (cold start; backend + frontend active)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 30 -LeaveRunning` -> success (warm start; backend reused)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode packaged -SkipSidecarBuild -HealthTimeoutSeconds 30` -> success (debug packaged host + bundled backend boot to healthy state)
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success
- `python -m oracle doctor` -> success with bundled `streamrip` and `spotdl` detected
- `python -m oracle status` -> success with healthy core metrics

## 5) Documentation Truth Status

- Tracked markdown files: 26 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Archived plan pointer: `docs/MASTER_PLAN_EXPANDED.md`

## 6) Active Gaps

1. Blank-machine installer install-and-launch validation is still pending outside this workstation.
2. Native audio (`miniaudio`) production soak validation across real devices/sessions.
3. Runtime/source separation policy is still partial beyond the new dedicated `.lyra-build` staging root.
4. One successful live packaged/runtime-backed tier-2 streamrip acquisition proof is still pending.
5. Mantine/Figma foundation is live across the main workspace plus key secondary surfaces, but not yet across every legacy route/panel.

## 7) Immediate Next Pass

1. Run a blank-machine installer install-and-launch validation to confirm bundled sidecar + runtime-tool discovery outside the dev box.
2. Run one live packaged/runtime-backed streamrip acquisition with configured Qobuz credentials.
3. Run parity-hardening acceptance as an extended 4-hour soak with pause/seek/repeat/recovery coverage.
4. Continue runtime/source separation cleanup after the external installer proof.
5. Extend the Mantine foundation into any remaining legacy routes and system panels that still rely on older primitives.
6. Continue graph/credits/structure depth passes once release-gate proof is complete.
