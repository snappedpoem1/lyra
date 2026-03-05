# Lyra Oracle Project State

Last audited: March 5, 2026 (America/New_York)

This is a reality-based snapshot of the repository and running system state as verified from this workspace.

## 1) Repository And Delivery State

- Branch: `main`
- Working tree: clean
- Latest commit: `ff4ebb3` (`policy: require session-log and markdown-state updates on delivery`)
- Previous major stabilization commit: `18e7702` (`Stabilize search/data flow, harden rewrite parsing, and refine Winamp-style UI`)

## 2) Stack And Architecture (Current)

- Backend: Python 3.12, Flask API (`lyra_api.py`, `oracle/api/*`)
- Data stores:
  - SQLite registry: `lyra_registry.db`
  - Chroma vector store: `chroma_storage/`
- Frontend: Electron direction with React/Vite renderer in `desktop/renderer-app/`
- Core domains under `oracle/`: search, scoring, vibes/playlists, enrichment, discovery, acquisition
- Runtime/source split contract documented in `docs/REPO_STRUCTURE.md`

## 3) Live Catalog And Runtime Metrics

From `python -m oracle status`:

- Tracks (total): 2,454
- Tracks (active): 2,454
- Embeddings: 2,454
- Scored tracks: 2,454
- Vibes: 9
- Queue pending: 2,009
- Spotify history rows: 127,312
- Spotify library rows: 4,026
- Playback events: 30,680

## 4) Services And Integrations State

From `scripts/ensure_workspace_docker.ps1` + `python -m oracle doctor` + desktop smoke:

- Docker daemon: running
- Healthy target containers: `prowlarr`, `rdtclient`, `slskd`
- Acquisition tiers:
  - Tier 1 Qobuz: OK
  - Tier 2 Streamrip: configured but not active in status output
  - Tier 3 slskd: OK
  - Tier 4 Real-Debrid: OK
  - Tier 5 SpotDL: OK
- Lidarr endpoint: reachable
- LLM provider: openai-compatible via Groq (`llama-3.3-70b-versatile`), API key present
- LM Studio: offline (non-blocking in current profile)

## 5) Verification Results (This Audit Run)

### Test and build

- `python -m pytest -q` -> `64 passed`
- `npm run test` (`desktop/renderer-app`) -> `1 file / 3 tests passed`
- `npm run build` (`desktop/renderer-app`) -> success (`vite` production bundle built)

### End-to-end smoke

- `scripts/smoke_desktop.ps1 -AllowLlmFailure` -> passed
- Verified endpoints/flows in smoke output:
  - health
  - vibes
  - library artists/tracks/albums
  - artist detail
  - album detail
  - playlist detail
  - flow
  - stream
  - search
  - discovery
  - queue

## 6) Playlist Reality Check Against User Export

From `scripts/analyze_playlist_export.py` against:
`C:\Users\Admin\Documents\LYRA PROJECT\Playlist1.json`

- Matched: 651 / 1390 (46.8%)
- Missing: 739

Interpretation:
- The system can build reality-based playlists from the local library.
- Parity with the full export is limited by local library coverage and match quality, not by fabricated recommendations.

## 7) UI State (Current Direction)

- Desktop renderer builds and tests pass.
- Live backend data paths are active; fixture masking was removed for normal runtime in prior stabilization work.
- Styling was moved away from retro-jukebox cues toward a more polished Winamp-successor direction while keeping the existing palette and UHD scaling support.
- Recommendation surfaces are wired to live queue-backed/backend-backed data in normal mode.

## 8) Documentation Truth Status

Checked all tracked markdown files (`git ls-files "*.md"`):

- Tracked markdown files: 14
- Relative markdown link check: no broken relative links found
- Historical file explicitly marked as old by design:
  - `docs/MASTER_PLAN_EXPANDED_OLD.md`

Docs with explicit current-state role:

- `README.md`
- `docs/MASTER_PLAN_EXPANDED.md`
- `docs/MISSING_FEATURES_REGISTRY.md`
- `docs/WORKLIST.md` (last updated: March 4, 2026)
- `docs/REPO_STRUCTURE.md`

## 9) Known Gaps / Not Fully Closed Yet

- Live playback ingestion verification still depends on active foobar2000 + BeefWeb session confirmation.
- Agent action responses are available but deeper app-side action execution remains partial.
- Artist graph exists and is usable, but richer edge semantics are still pending for full discovery depth.
- Runtime artifacts are still near source and should eventually move to a stricter runtime root model.
- Spotify history to local-track matching quality can still improve for better export parity.

## 10) What Is 100% Confirmed In This Audit

- Core backend tests pass.
- Renderer tests and production build pass.
- Docker target services needed for acquisition stack are healthy.
- API and desktop contract smoke passes across key routes.
- LLM configuration is live and reachable with selected model.
- Documentation link integrity for tracked markdown files is currently clean.

## 11) Suggested Next Reality Pass (If Continuing Immediately)

1. Run a live foobar2000 playback session and verify new `playback_history` inserts in real time.
2. Improve Spotify export matching normalization/fuzzy logic and re-run playlist audit to raise match coverage.
3. Continue moving mutable runtime outputs out of repo-root proximity to tighten source/runtime separation.
