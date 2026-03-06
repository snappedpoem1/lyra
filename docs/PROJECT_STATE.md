# Lyra Oracle Project State

Last audited: March 6, 2026 (America/New_York)

This is the current repo/runtime snapshot verified from this workspace.

## 1) Repository State

- Branch: `main`
- Working tree: dirty (active implementation session in progress)
- Head commit: `f3e0c0f` (validated unified-app checkpoint before current broker pass)

## 2) Architecture State (Current)

- Backend: Python 3.12 + Flask (`lyra_api.py`, `oracle/api/*`)
- Stores:
  - SQLite registry: `lyra_registry.db`
  - Chroma storage: `chroma_storage/`
- Desktop runtime:
  - Tauri host in `desktop/renderer-app/src-tauri/`
  - React/Vite renderer in `desktop/renderer-app/`
  - Canonical launcher: `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev`
  - Docker is not required and not auto-started in unified launch path
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
  - Oracle action routing now performs concrete backend actions for:
    `queue_tracks`, `start_vibe`, `start_playlust`, and `switch_chaos_intensity`
  - Recommendation broker contract now exposed at:
    - `POST /api/recommendations/oracle`
  - Broker currently fuses:
    - local radio engine (`flow`, `chaos`, `discovery`)
    - Last.fm similar-track signals when API key is configured
    - ListenBrainz community top-recording signals
  - Broker responses include:
    - provider weights
    - provider availability/degradation messages
    - per-track provenance signals
    - acquisition leads for tracks not yet in the local library

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

- `python -m pytest -q` -> `88 passed`
- `python -m pytest -q tests/test_recommendation_broker_contract.py tests/test_oracle_actions_contract.py tests/test_player_api_contract.py tests/test_player_service.py` -> `17 passed`
- `cd desktop\renderer-app; npm run test` -> `1 file / 3 tests passed`
- `cd desktop\renderer-app; npm run build` -> success
- `cd desktop\renderer-app; npm run tauri:build -- --debug` -> success (MSI + NSIS debug bundles)
- `powershell -ExecutionPolicy Bypass -File scripts/build_backend_sidecar.ps1` -> success (`desktop/renderer-app/src-tauri/bin/lyra_backend.exe`)
- `powershell -ExecutionPolicy Bypass -File scripts/smoke_step1_step2.ps1 -StartupTimeoutSeconds 60 -SoakSeconds 20` -> success (full Step 1/2 path, including canonical player API + SSE checks)
- `powershell -ExecutionPolicy Bypass -File scripts/parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 10 -StartupTimeoutSeconds 60` -> success (smoke + forced restart recovery + SSE + stability soak)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 90 -LeaveRunning` -> success (cold start; backend + frontend active)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode dev -HealthTimeoutSeconds 30 -LeaveRunning` -> success (warm start; backend reused)
- `powershell -ExecutionPolicy Bypass -File scripts/start_lyra_unified.ps1 -Mode packaged -SkipSidecarBuild` -> expected non-zero failure with clear error when packaged host binary is absent
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` -> success
- `python -m oracle status` -> success with healthy core metrics

## 5) Documentation Truth Status

- Tracked markdown files: 26 (`git ls-files "*.md"`)
- Relative markdown link check across tracked docs: passing
- Forward plan authority: `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- Archived plan pointer: `docs/MASTER_PLAN_EXPANDED.md`

## 6) Active Gaps

1. Clean-machine packaged installer validation for `lyra_backend.exe` sidecar flow.
2. Native audio (`miniaudio`) production soak validation across real devices/sessions.
3. Recommendation outcome logging/feedback loop is not yet captured for broker acceptance, skips, and replays.
4. Acquisition radar is visible in UI but not yet wired to one-click acquisition actions.
5. Runtime/source separation policy is still partial.

## 7) Immediate Next Pass

1. Run packaged installer validation on a clean machine to confirm sidecar discovery/runtime.
2. Run parity-hardening acceptance (4-hour soak + pause/seek/repeat/recovery across restart).
3. Add broker feedback/event logging so recommendation quality can be measured by accepts/skips/replays.
4. Turn acquisition radar leads into one-click forward actions from the Oracle surface.
