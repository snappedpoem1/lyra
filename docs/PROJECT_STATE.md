# Lyra Oracle Project State

Last audited: March 6, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: local changes pending for session `S-20260306-14` plus unrelated renderer/UI edits already present in the workspace
- Latest committed baseline before this audit: `9464d06` (`S-20260306-13` installed runtime validation docs)

## 2) Architecture State (Current)

- Backend: Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry: `lyra_registry.db`
  - Chroma storage: `chroma_storage/`
- Desktop runtime:
  - Tauri host in `desktop/renderer-app/src-tauri/`
  - React/Vite renderer in `desktop/renderer-app/`
  - Renderer component foundation includes Mantine (`@mantine/core`, `@mantine/hooks`) with a Lyra-specific theme layer
  - Canonical launcher: `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev`
  - Packaged runtime builder: `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1`
  - Docker is not required and not auto-started in the unified launch path
  - Legacy external-service bootstrap is opt-in only via `LYRA_BOOTSTRAP_LEGACY_SERVICES=1`
  - Unified runtime shell is active: Library, Semantic, Deep Cut, Now Playing, Queue, Artist Context, Oracle
  - Secondary renderer surfaces use the same Mantine-based foundation: settings route, right rail, track dossier drawer, developer HUD, companion shell
- Playback authority:
  - Canonical backend player domain in `oracle/player/*`
  - Persisted `player_state` and `player_queue` tables
  - API surface: `/api/player/*`
  - `/ws/player` is the SSE event stream
  - `/api/playback/record` remains compatibility-only
- Oracle and recommendation state:
  - Acquisition bootstrap snapshot is exposed in `/api/health` and `/api/status` without Docker boot
  - Runtime-service packaging policy is exposed at `GET /api/runtime/services`
  - Oracle action routing performs concrete backend actions for `queue_tracks`, `start_vibe`, `start_playlust`, `switch_chaos_intensity`, and `request_acquisition`
  - Recommendation broker contract is exposed at:
    - `POST /api/recommendations/oracle`
    - `POST /api/recommendations/oracle/feedback`
  - Broker fuses local radio, Last.fm similar-track signals, and ListenBrainz community top-recording signals
  - Recommendation feedback is persisted in SQLite and used as a lightweight ranking bias
- Acquisition and runtime packaging:
  - Bundled tool lookup exists for `streamrip` and `spotdl` via `runtime/bin`, `runtime/tools`, and `runtime/acquisition-tools`
  - Bundled acquisition helper executables are built and staged by:
    - `scripts/build_runtime_tools.ps1`
    - `scripts/build_packaged_runtime.ps1`
  - Frozen sidecar packaging now includes explicit hidden imports for `oracle.api.blueprints.*` so the bundled backend exposes the real Flask API contract after PyInstaller onefile packaging
  - Packaged proof scripts now active:
    - `scripts/validate_clean_machine_install.ps1`
    - `scripts/validate_packaged_streamrip.ps1`
    - `scripts/packaged_host_smoke.ps1`
    - `scripts/validate_installed_runtime.ps1`
  - `scripts/packaged_host_smoke.ps1` now claims port `5000` before launch so packaged validation cannot pass against an unrelated already-running backend
  - `scripts/parity_hardening_acceptance.ps1` now writes log and JSONL snapshot artifacts under `.lyra-build/logs/parity`, runs transport mutations during soak, and captures failure diagnostics automatically
  - `scripts/parity_hardening_acceptance.ps1` runs packaged proof scripts as pre-flight
  - `oracle/acquirers/streamrip.py` uses streamrip 2.x syntax by default:
    `rip -f <output_dir> search <source> track <query> --first`
  - Generated packaged artifacts stage under:
    - `.lyra-build/bin`
    - `.lyra-build/bin/runtime/bin`
  - Tauri packaged resources consume `.lyra-build/bin`
  - Packaged backend startup exports `LYRA_RUNTIME_ROOT` and prepends bundled runtime bins to `PATH`
  - Packaged runtime-root resolution is hardened for installed layouts where the sidecar may live in:
    - `bin\`
    - `resources\`
    - `resources\bin\`
  - Installed or installed-style validation now covers:
    - host exe detection
    - sidecar candidate detection
    - runtime/bin candidate detection
    - packaged host launch via explicit installed exe override
- Frozen-runtime hardening:
  - `lyra_api.py` uses `Path(sys.executable).parent` for frozen `PROJECT_ROOT`
  - `oracle/api/app.py` derives HuggingFace cache roots from `oracle.config.PROJECT_ROOT`
  - backend sidecar build collects broader Oracle subpackages so frozen installs include dynamic imports required on clean machines
- Spotify import background path:
  - `POST /api/spotify/import` triggers a non-blocking Spotify history import
  - `GET /api/spotify/import/status` reports running state, last result, and last error

## 3) Runtime Metrics

From `python -m oracle status`:

- Tracks total: 2,454
- Tracks active: 2,454
- Embeddings: 2,454
- Scored tracks: 2,454
- Vibes: 9
- Queue pending: 2,036
- Spotify history rows: 127,572
- Spotify library rows: 4,026
- Playback events: 30,680

## 4) Verification Results (This Audit)

- `python -m pytest -q` -> `106 passed`
- `cd desktop\renderer-app; npm run test` -> `1 file / 3 tests passed`
- `cd desktop\renderer-app; npm run build` -> success
- `cd desktop\renderer-app; npm run tauri:build -- --debug` -> success (debug host rebuilt, MSI and NSIS bundles produced)
- `powershell -ExecutionPolicy Bypass -File scripts/build_backend_sidecar.ps1` -> success (`.lyra-build/bin/lyra_backend.exe`; frozen sidecar launch check passed against the bundled API contract)
- `powershell -ExecutionPolicy Bypass -File scripts/build_runtime_tools.ps1` -> success (`runtime/bin/*.exe` plus staged `.lyra-build/bin/runtime/bin` helpers)
- `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1 -SkipLaunchCheck -SkipToolSmokeCheck` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/validate_clean_machine_install.ps1` -> success (artifact presence, Tauri config, executable smoke checks, simulated install layout check)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_packaged_streamrip.ps1` -> success (binary presence, version, `is_available()`, command syntax)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_packaged_streamrip.ps1 -LiveAcquire` -> success (live Qobuz acquisition; G-034 closed)
- `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45` -> success (deterministic packaged-host launch smoke after claiming port `5000`)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_installed_runtime.ps1 -InstalledRoot desktop\renderer-app\src-tauri\target\debug -HealthTimeoutSeconds 45` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/smoke_step1_step2.ps1 -StartupTimeoutSeconds 60 -SoakSeconds 20` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 10 -StartupTimeoutSeconds 60` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SkipInstallerProof -SoakSeconds 45 -CheckpointIntervalSeconds 10 -ActionIntervalSeconds 8 -StartupTimeoutSeconds 60` -> success (mutating parity soak with pause/resume, seek, next/previous, mode changes, and checkpoint artifacts)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 90 -LeaveRunning` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode packaged -SkipSidecarBuild -HealthTimeoutSeconds 30` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success
- `python -m oracle doctor` -> success with bundled `streamrip` and `spotdl` detected
- `python -m oracle status` -> success with healthy core metrics

## 5) Documentation Truth Status

- Tracked markdown files: 27 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Archived plan pointer: `docs/MASTER_PLAN_EXPANDED.md`

## 6) Active Gaps

1. Blank-machine installer install-and-launch validation is still pending outside this workstation.
2. Native audio (`miniaudio`) production soak validation across real devices and a full 4-hour long-session run.
3. Runtime/source separation is still partial beyond the dedicated `.lyra-build` staging root.
4. Mantine/Figma foundation is live across the main workspace plus key secondary surfaces, but not yet across every legacy route or panel.

## 7) Immediate Next Pass

1. Run a blank-machine installer install-and-launch validation to confirm bundled sidecar and runtime-tool discovery outside the dev box.
2. Run parity-hardening acceptance as an extended 4-hour soak with pause, seek, repeat, and restart recovery coverage.
3. Continue runtime/source separation cleanup after the external installer proof.
4. Extend the Mantine foundation into any remaining legacy routes and system panels.
5. Continue graph, credits, and structure depth passes once release-gate proof is complete.
