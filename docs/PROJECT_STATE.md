# Lyra Oracle Project State

Last audited: March 7, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: local changes pending for sessions `S-20260306-17` through `S-20260307-05`
- Latest committed baseline before this audit: `1d09322` (`S-20260306-16` qobuz tier1 fix docs)
- Program state:
  - the governance-first split modernization sequence is now locally aligned through Wave 2
  - Wave 3 (`LYRA_DATA_ROOT` and mutable-data authority) is now locally closed through the runtime contract plus explicit migrate-now/defer actions
  - Wave 4 desktop stack modernization is now locally landed through the Tauri 2 host/runtime upgrade and acceptance pass
  - Wave 5 can now proceed locally while blank-machine proof remains blocked-external and the 4-hour soak is intentionally deferred until a later release-gate window
  - `docs/PHASE_EXECUTION_COMPANION.md` now carries the execution-grade phase sequence, iteration order, and owner-split rules from Wave 3 through the committed long-horizon end state
  - later metadata/product-depth work remains out of scope until earlier runtime/release gates stay green
- Governance state:
  - root `AGENTS.md` plus scoped lane briefs/instruction files exist in the working tree
  - nearest-directory `AGENTS.md` files now exist for `oracle/`, `desktop/renderer-app/`, `scripts/`, and `docs/`
  - `docs/agent_briefs/tandem-wave-protocol.md` now defines the standing two-agent split protocol for future shared waves
  - Tauri is the only active desktop build authority
  - Windows-first CI/release governance is defined in:
    - `.github/workflows/windows-pr.yml`
    - `.github/workflows/windows-release-governance.yml`
  - explicit toolchain authority is pinned in:
    - `.python-version`
    - `.node-version`
    - `rust-toolchain.toml`
  - build provenance is emitted by `scripts/write_build_manifest.ps1`

## 2) Architecture State (Current)

- Backend: Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry default: `LYRA_DATA_ROOT\db\lyra_registry.db`
  - Chroma storage default: `LYRA_DATA_ROOT\chroma\`
- Desktop runtime:
  - Tauri host in `desktop/renderer-app/src-tauri/` now runs on the Tauri 2 desktop contract
  - React/Vite renderer in `desktop/renderer-app/`
  - `desktop/package.json` is now a thin Tauri wrapper with no Electron metadata or dependencies
  - `@tauri-apps/api` and `@tauri-apps/cli` are now on the 2.x line
  - `desktop/renderer-app/src-tauri/tauri.conf.json` now uses config schema `2`
  - host tray behavior is now implemented through the Tauri 2 tray API and the global-shortcut plugin
  - the main desktop capability file now lives at `desktop/renderer-app/src-tauri/capabilities/default.json`
  - Renderer component foundation includes Mantine (`@mantine/core`, `@mantine/hooks`) with a Lyra-specific theme layer
  - Mantine is now treated as infrastructure rather than visible design authority; high-traffic surfaces are being restyled into a more bespoke shell language
  - Canonical launcher: `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev`
  - Packaged runtime builder: `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1`
  - Docker is not required and not auto-started in the unified launch path
  - Legacy external-service bootstrap is opt-in only via `LYRA_BOOTSTRAP_LEGACY_SERVICES=1`
  - Unified runtime shell is active: Library, Semantic, Deep Cut, Now Playing, Queue, Artist Context, Oracle
  - Secondary renderer surfaces use the same Mantine-based foundation: settings route, right rail, backend/doctor diagnostics panels, track dossier drawer, developer HUD, companion shell
    - Search mode controls, the semantic search hero, Oracle mode controls, and the artist route now also use Mantine primitives in the active runtime
    - Home, Queue, playlists landing, playlist detail, Oracle, Vibe Library, and the Library route shell now use a bespoke "studio deck" treatment on top of the shared renderer foundation
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
  - `LYRA_DATA_ROOT` is now the config-owned writable-data authority for SQLite, Chroma, logs, temp, runtime state, HuggingFace cache, staging/downloads, and generated reports/playlists/vibes artifacts
  - dev default data root resolves to `%LOCALAPPDATA%\Lyra\dev`
  - frozen or installed default data root resolves to `%LOCALAPPDATA%\Lyra`
  - `.lyra-build` remains build/runtime artifact staging only, not user data
  - legacy repo-root mutable data is explicitly detected and can only be reused via `LYRA_USE_LEGACY_DATA_ROOT=1`
  - explicit migration flow now exists in both CLI and runtime API:
    - `python -m oracle.cli data-root status|migrate|defer`
    - `GET /api/runtime/data-root`
    - `POST /api/runtime/data-root/migrate`
    - `POST /api/runtime/data-root/defer`
  - Bundled tool lookup exists for `streamrip` and `spotdl` via `runtime/bin`, `runtime/tools`, and `runtime/acquisition-tools`
  - Bundled acquisition helper executables are built and staged by:
    - `scripts/build_runtime_tools.ps1`
    - `scripts/build_packaged_runtime.ps1`
  - Runtime-generated defaults are now routed through explicit config-owned roots under `.lyra-build`:
    - logs -> `.lyra-build/logs`
    - temp scratch -> `.lyra-build/tmp`
    - runtime state -> `.lyra-build/state`
    - model cache -> `.lyra-build/cache/hf`
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
  - Release governance now records Windows artifact hashes in `.lyra-build/manifests/windows-release-gate.json`
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
  - `oracle.config` and `lyra_api.py` now both use `Path(sys.executable).parent` for frozen `PROJECT_ROOT`
  - `lyra_api.py`, `oracle/api/app.py`, `oracle/worker.py`, and `oracle/embedders/clap_embedder.py` derive HuggingFace cache roots from config-owned generated paths instead of repo-root `hf_cache`
  - `oracle/runtime_state.py` now writes profile/pause state under the active data root while still reading legacy repo-root files for compatibility
  - backend sidecar build collects broader Oracle subpackages so frozen installs include dynamic imports required on clean machines
- Spotify import background path:
  - `POST /api/spotify/import` triggers a non-blocking Spotify history import
  - `GET /api/spotify/import/status` reports running state, last result, and last error

## 3) Runtime Metrics

From `.venv\Scripts\python.exe -m oracle.status` after the Wave 3 cutover on this workstation:

- the fresh default data root responds cleanly but does not yet contain migrated library tables
- status currently reports `(table missing)` counts until the legacy repo-root state is migrated or explicitly reused via `LYRA_USE_LEGACY_DATA_ROOT=1`
- the pre-cutover library data still exists in the legacy repo-root layout and is now treated as migration-needed state rather than the silent default

## 4) Verification Results (This Audit)

- `python -m pytest -q` -> `106 passed`
- `cd desktop\renderer-app; npm run test` -> `1 file / 3 tests passed`
- `cd desktop\renderer-app; npm run build` -> success
- `cd desktop\renderer-app; npm run test` -> revalidated after the bespoke-shell route pass
- `cd desktop\renderer-app; npm run build` -> revalidated after the bespoke-shell route pass
- `cd desktop\renderer-app; npm run test` -> revalidated after Oracle + Vibe Library shell pass
- `cd desktop\renderer-app; npm run build` -> revalidated after Oracle + Vibe Library shell pass
- `cd desktop\renderer-app; npm run test` -> revalidated after Library + playlist-detail shell pass
- `cd desktop\renderer-app; npm run build` -> revalidated after Library + playlist-detail shell pass
- `cd desktop\renderer-app; npm run test` -> revalidated after backend/doctor system panel shell pass
- `cd desktop\renderer-app; npm run build` -> revalidated after backend/doctor system panel shell pass
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
- `python -m oracle.cli credits enrich --limit 15` -> success (`processed=15 found=0 empty=15 failed=0`)
- `python -m oracle.cli structure analyze --limit 15` -> success (`track_structure` rows `159 -> 172`)
- `python -m oracle.cli discover listenbrainz --limit-artists 80 --tracks-per-artist 8` -> success (`136` new queue candidates)
- `python -m oracle.cli acquire prioritize --limit 500` -> success after fixing `priority_score` column usage
- `python -m oracle.cli drain --limit 2 --workers 1 --max-tier 4` -> partial success (`1` streamrip acquisition ingested, `1` retry re-queued)
- `python -m oracle.cli drain --limit 1 --workers 1 --max-tier 4` -> Tier 1 Qobuz success after fixing the service URL runtime bug; duplicate-backed post-flight handling now resolves against the exact downloaded queue row, completing true duplicate hits and immediately retrying mismatch cases with an explicit error instead of stale re-queue drift
- `python -m pytest -q` -> success (`109 passed`)
- `.venv\Scripts\python.exe -m pytest -q` -> success (`114 passed`)
- `.venv\Scripts\python.exe -m oracle.doctor` -> warnings only for optional external companions; bundled runtime tools and local core stores healthy
- `C:/MusicOracle/.venv/Scripts/python.exe -m pytest -q` -> success (`115 passed`)
- `.venv\Scripts\python.exe -m pytest -q` -> success (`119 passed`)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_data_root_contract.ps1` -> success
- `.venv\Scripts\python.exe -m oracle.doctor` -> warnings only / system functional under the new data-root contract
- `.venv\Scripts\python.exe -m oracle.status` -> success (fresh data-root status path responds cleanly)
- `cd desktop\renderer-app; npm run test:ci` -> success (`1 file / 3 tests passed`)
- `cd desktop\renderer-app; npm run build` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/build_packaged_runtime.ps1 -SkipLaunchCheck -SkipToolSmokeCheck` -> success
- `cd desktop\renderer-app; npm run tauri:build -- --debug` -> success (debug host rebuilt, MSI and NSIS bundles produced after Electron archival)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_installed_runtime.ps1 -InstalledRoot desktop\renderer-app\src-tauri\target\debug -HealthTimeoutSeconds 45` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/write_build_manifest.ps1 -OutputPath .lyra-build/manifests/windows-release-gate.json` -> success
- `.venv\Scripts\python.exe -m pytest -q` -> success (`126 passed`)
- `.venv\Scripts\python.exe -m oracle.doctor` -> warnings only / system functional during Wave 3 closeout
- `.venv\Scripts\python.exe -m oracle.status` -> success (fresh data-root path still reports empty-table counts until library data is migrated or explicitly reused)
- `powershell -ExecutionPolicy Bypass -File scripts/validate_data_root_contract.ps1` -> success
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success
- `cd desktop\renderer-app; npm run test:ci` -> success (`3 files / 26 tests passed`) after the Wave 4 renderer prep + Tauri 2 host migration
- `cd desktop\renderer-app; npm run build` -> success after the Wave 4 Tauri 2 dependency uplift
- `cd desktop\renderer-app; npm run tauri:build -- --debug` -> success after the Wave 4 Tauri 2 host migration (debug host rebuilt, MSI and NSIS bundles produced)
- `powershell -ExecutionPolicy Bypass -File scripts/packaged_host_smoke.ps1 -HealthTimeoutSeconds 45` -> success after the Wave 4 Tauri 2 host migration

## 5) Documentation Truth Status

- Tracked markdown files: 50 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Execution companion: `docs/PHASE_EXECUTION_COMPANION.md`
- Archived plan pointer: `docs/MASTER_PLAN_EXPANDED.md`
- Current governance wave:
  - Wave 1 doc/agent alignment is locally landed
  - Wave 2 build/release governance is locally landed and validated
  - Wave 3 runtime/data-root contract is locally landed and validated, including explicit migrate-now/defer CLI and API flow
  - Wave 4 desktop stack modernization is locally landed and validated against the packaged host contract
  - Wave 5 is now the next implementation wave while blank-machine proof remains blocked-external and soak work is deferred
  - a standing tandem-wave protocol now defines how Codex and Copilot split future waves without overlapping file ownership
  - the new execution companion turns Waves 3 through 11 into one iteration-level committed phase track without replacing the roadmap authority

## 6) Active Gaps

1. Blank-machine installer install-and-launch validation is still pending outside this workstation and is currently blocked by the lack of a clean Windows machine or VM.
2. Native audio (`miniaudio`) production soak validation across real devices and a full 4-hour long-session run is intentionally deferred until a later release-gate window.
3. Mantine/Figma foundation plus the bespoke shell pass are live across the main workspace, Home, Queue, Playlists, playlist detail, Search, Oracle, Vibe Library, the Library route shell, backend/doctor system panels, Artist, and key secondary surfaces, but not yet across every remaining legacy route or panel.

## 7) Immediate Next Pass

1. Open Wave 5 provider-contract and recommendation-core work on top of the settled Wave 4 host/runtime contract.
2. Run blank-machine installer install-and-launch proof once a clean Windows machine or VM is available.
3. Revisit the 4-hour parity/audio soak when the release-gate window is reopened.
4. Resume later metadata/product-depth expansion only after the earlier runtime/release gates stay green.
