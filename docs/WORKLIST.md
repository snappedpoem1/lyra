# Worklist

Last updated: March 6, 2026

This file tracks active execution work only.

## Completed Recently

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

## In Progress (Current Session S-20260306-23)

- Active: Wave 2 closeout and docs synchronization after local CI/release-governance validation

## Order Of Operation (Highest Result First)

1. `LYRA_DATA_ROOT` cutover:
   - move mutable data authority out of repo-root assumptions
2. Blank-machine installer proof:
  - validate the packaged installer on a clean Windows machine
3. Final parity/audio soak closure:
  - execute the full 4-hour packaged/native validation run
4. Desktop stack modernization:
   - modernize Tauri/front-end toolchain only after governance and runtime contracts are aligned
5. Metadata/recommendation/provider expansion:
   - deepen provider contracts, provenance, and source integration
6. UI provenance and Oracle depth:
   - surface rationale, degraded states, and recommendation evidence where it matters

## Next Up

1. Implement the `LYRA_DATA_ROOT` cutover as the next runtime/source-separation pass.
2. Run the packaged installer on a clean Windows machine and confirm first launch.
3. Execute the full 4-hour parity/audio soak with the finalized packaged host contract.
4. Resume later metadata/product-depth waves only after the earlier runtime/release gates remain green.
