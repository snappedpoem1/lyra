# Lyra Oracle

Lyra Oracle is a local-first music intelligence app for personally owned libraries.

Tagline:

- Lyra: music oracle is what I am.
- Yeah its a music player, but I dont think you get it.

## Architecture Lock

- Tauri is the only supported desktop host path.
- Backend player (`oracle/player/*`) is canonical playback source of truth.
- UI transport controls call `/api/player/*`.
- `/ws/player` is an SSE event stream contract.
- Docker services are optional acquisition support, not required for daily local playback.
- Packaged builds now stage bundled acquisition helpers (`streamrip`, `spotdl`, `ffmpeg`, `ffprobe`) alongside the backend sidecar.

## Current Verified Local Snapshot (March 6, 2026)

- Tracks: 2,454
- Embeddings: 2,454
- Scored tracks: 2,454
- Vibes: 9
- Queue pending: 2,036
- Spotify history rows: 127,312
- Playback events: 30,680
- Backend tests: 88 passing

See `docs/PROJECT_STATE.md` for full audited detail.

## Core Capabilities

- Local scan/index/search/scoring
- Saved vibes and playlust generation
- Artist enrichment and graph discovery
- Acquisition waterfall orchestration
- Canonical backend player with queue/state persistence
- Unified modular player shell (Library, Now Playing, Queue, Oracle)

## Quick Start (Windows)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env
.venv\Scripts\python.exe -m oracle db migrate
```

Run unified app (backend + frontend, no Docker dependency):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_lyra_unified.ps1 -Mode dev
```

Alternative dev-only path (Tauri directly):

```powershell
cd desktop\renderer-app
npm install
npm run tauri:dev
```

### Runbook: What starts

- Tauri dev host (frontend runtime)
- Backend sidecar/API (health-gated via `/api/health`)
- Acquisition tier availability snapshot (best-effort, non-blocking)
- Packaged runtime builder (`scripts\build_packaged_runtime.ps1`) for sidecar + acquisition helper staging

### Runbook: What does not start

- Docker Desktop
- `scripts\ensure_workspace_docker.ps1`
- Any mandatory acquisition container bootstrap

## Validation Commands

```powershell
python -m pytest -q
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\smoke_desktop.ps1 -AllowLlmFailure
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Protocol

Every behavior-changing session must start with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

Use session-prefixed commits:

`[S-YYYYMMDD-NN] <type>: <description>`

## Key Docs

- `docs/ROADMAP_ENGINE_TO_ENTITY.md` - single forward plan authority
- `docs/PROJECT_STATE.md` - audited current truth
- `docs/WORKLIST.md` - active execution list
- `docs/MISSING_FEATURES_REGISTRY.md` - active gaps
- `docs/SESSION_INDEX.md` - session table of record
