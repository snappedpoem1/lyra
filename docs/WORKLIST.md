# Worklist

Last updated: March 6, 2026

This file tracks active execution work only.

## Completed Recently

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
- Live packaged streamrip acquisition proof is validated:
  - `scripts/validate_packaged_streamrip.ps1 -LiveAcquire` passed
  - G-034 is closed
- Spotify import background endpoints are live:
  - `POST /api/spotify/import`
  - `GET /api/spotify/import/status`
  - backend suite is now `106 passed`

## In Progress (Current Session S-20260306-13)

- Completed: installed-layout validation tooling, packaged runtime-root hardening, rebuilt debug bundle validation, and release-gate doc normalization

## Order Of Operation (Highest Result First)

1. Blank-machine installer validation:
   - Install the generated setup on a clean Windows VM or second machine
   - Confirm first launch works with bundled sidecar and runtime tools only
2. Parity hardening acceptance as release gate:
   - Extend from the passing short acceptance run to a 4-hour soak
   - Confirm canonical player, SSE, forced-restart recovery, and long-session stability
3. 4-hour gaming/listening soak:
   - Confirm no crashes or dropouts
   - Confirm tray and media keys remain responsive
   - Confirm no queue drift
4. Remaining legacy UI surfaces:
   - Extend the Mantine foundation where it still improves day-to-day usability

## Next Up

1. Run a blank-machine installer install-and-launch proof on a clean Windows VM.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild` as a 4-hour soak.
3. Continue runtime/source separation cleanup after the external installer proof.
4. Extend the Mantine foundation across remaining legacy routes and system panels where useful.
5. Continue graph, credits, and structure depth passes after release-gate proof.
