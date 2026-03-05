# Lyra Oracle

Lyra Oracle is a local-first music intelligence system for a personally owned library.
It combines library indexing, CLAP embeddings, semantic search, dimensional scoring, playlist generation, artist enrichment, acquisition tooling, and a desktop UI on top of a Python/Flask backend.

It is built for people who want more than a media player and less than a black-box streaming recommendation engine.

## What It Does

- Scans and indexes a local music library
- Generates CLAP embeddings for semantic and hybrid search
- Scores tracks across 10 emotional dimensions
- Builds saved vibes, playlist runs, and 4-act Playlust arcs
- Enriches artists with biography, context, credits, and graph relationships
- Supports discovery, deep-cut hunting, and oracle-style recommendation flows
- Includes acquisition and library-management tooling for a local-first workflow

## Status

Current local audited snapshot:

- 2,454 indexed tracks
- 2,454 scored tracks
- 2,454 embeddings
- 950 artists
- 1,815 graph connections
- working CLI, Flask API, and desktop renderer

This is a working system, not a finished product. The core platform exists. The remaining work is mostly in runtime activation, graph depth, and polishing a few user-facing integration paths.

## Core Capabilities

### Library And Search

- Scan, index, score, and diagnose via [`oracle/cli.py`](oracle/cli.py)
- Semantic and hybrid search via [`oracle/search.py`](oracle/search.py) and [`oracle/api/blueprints/search.py`](oracle/api/blueprints/search.py)
- 10-dimensional emotional scoring via [`oracle/scorer.py`](oracle/scorer.py)

### Playlists And Vibes

- Saved vibes and playlist persistence via [`oracle/vibes.py`](oracle/vibes.py)
- Playlist reasoning and explainability via [`oracle/explain.py`](oracle/explain.py)
- 4-act Playlust arc generation via [`oracle/playlust.py`](oracle/playlust.py)

### Discovery And Enrichment

- Deep-cut discovery via [`oracle/deepcut.py`](oracle/deepcut.py)
- Artist biography enrichment via [`oracle/enrichers/biographer.py`](oracle/enrichers/biographer.py)
- Credit mapping via [`oracle/enrichers/credit_mapper.py`](oracle/enrichers/credit_mapper.py)
- Artist graph building via [`oracle/graph_builder.py`](oracle/graph_builder.py)
- Shrine and constellation endpoints via [`oracle/api/blueprints/enrich.py`](oracle/api/blueprints/enrich.py)
- Oracle discovery endpoints via [`oracle/api/blueprints/discovery.py`](oracle/api/blueprints/discovery.py)

### Acquisition

The acquisition stack is a 5-tier waterfall:

1. Qobuz
2. Streamrip
3. Slskd
4. Real-Debrid / Prowlarr
5. SpotDL / yt-dlp fallback

Most of that logic lives under [`oracle/acquirers/`](oracle/acquirers/).

## What Is Still In Progress

- Playback learning still needs a real foobar2000 + BeefWeb session to prove that events are landing in `playback_history`
- The command palette now talks to the backend agent, but agent actions are not yet deeply wired into desktop behavior
- The artist graph exists but still needs richer edge types for the full cultural-oracle vision
- Runtime data still sits close to source in ways that should eventually be cleaned up

## Architecture

High-level repo shape:

- [`oracle/`](oracle/) - core Python package
- [`oracle/api/`](oracle/api/) - Flask app factory and blueprints
- [`desktop/renderer-app/`](desktop/renderer-app/) - React + Vite desktop renderer
- [`lyra_api.py`](lyra_api.py) - API entry point
- [`lyra_registry.db`](lyra_registry.db) - SQLite registry
- [`chroma_storage/`](chroma_storage/) - vector store
- [`scripts/`](scripts/) - operational scripts
- [`docs/`](docs/) - current docs, gap registry, and reference distillation

## Quick Start

Windows, from the repo root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env
.venv\Scripts\python.exe -m oracle db migrate
```

Run the API:

```powershell
.venv\Scripts\python.exe lyra_api.py
```

Run a few CLI checks:

```powershell
.venv\Scripts\python.exe -m oracle doctor
.venv\Scripts\python.exe -m oracle status
.venv\Scripts\python.exe -m oracle search --query "dark ambient with glitchy textures" --n 10
.venv\Scripts\python.exe -m oracle perf clap-status
```

CLAP runtime controls:

- `oracle perf clap-status` - show shared CLAP runtime handles
- `oracle perf clap-unload` - force-evict shared CLAP handles
- `oracle perf clap-unload --idle-only` - evict only idle handles (uses `LYRA_CLAP_IDLE_UNLOAD_SECONDS`)
- `LYRA_CLAP_PREWARM=1` - prewarm CLAP during API startup
- `LYRA_CLAP_PREWARM_MODE=background|sync` - choose async or blocking prewarm mode
- `LYRA_CLAP_SKIP_LOCAL_PROBE=1` - skip local-only revision probe and load directly

Run the desktop renderer:

```powershell
cd desktop\renderer-app
npm install
npm run dev
```

Reality checks (recommended before judging recommendation quality):

```powershell
# End-to-end backend/UI contract smoke
powershell -ExecutionPolicy Bypass -File scripts/smoke_desktop.ps1 -AllowLlmFailure

# Audit a playlist export against your actual local library
.venv\Scripts\python.exe scripts\analyze_playlist_export.py --playlist-json "C:\Users\Admin\Documents\LYRA PROJECT\Playlist1.json"

# Refresh factual artist enrichment + graph edges used by Artist/Constellation pages
.venv\Scripts\python.exe -m oracle biographer enrich-all --limit 80
.venv\Scripts\python.exe -m oracle graph dimension-edges --threshold 0.60 --top-k 8
```

For production-like behavior in the desktop app, keep `fixtureMode` disabled in Settings so all routes use live backend data.

## Session Tracking

Every work session that changes observable behavior should be logged so all agent tools
(Copilot, Claude Code, Codex) stay aligned on the same project reality.

**Start a new session:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

This creates `docs/sessions/YYYY-MM-DD-my-work.md` from the template and adds a row to
`docs/SESSION_INDEX.md`. Use the printed Session ID as the commit message prefix:

```
[S-20260305-01] feat: add hybrid search ranking fix
```

**Session protocol (short version):**

1. Run `scripts/new_session.ps1` to create the log file
2. Do the work
3. Update `docs/PROJECT_STATE.md` if metrics or architecture changed
4. Update `docs/WORKLIST.md` if done/next items changed
5. Fill in the session log result and commit with the session prefix

See [`AGENTS.md`](AGENTS.md) for the full session rules and ground-truth file list.
See [`docs/SESSION_INDEX.md`](docs/SESSION_INDEX.md) for all past sessions.

## Key Docs

- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) - full audited project state snapshot
- [`docs/SESSION_INDEX.md`](docs/SESSION_INDEX.md) - table of all work sessions
- [`docs/MASTER_PLAN_EXPANDED.md`](docs/MASTER_PLAN_EXPANDED.md) - current high-level project status
- [`docs/MISSING_FEATURES_REGISTRY.md`](docs/MISSING_FEATURES_REGISTRY.md) - real gaps, partials, and integration issues
- [`docs/WORKLIST.md`](docs/WORKLIST.md) - short done / todo list
- [`docs/REFERENCE_INSIGHTS.md`](docs/REFERENCE_INSIGHTS.md) - distilled lessons from historical references
- [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) - current working memory snapshot

## Current Priorities

1. Verify live playback ingestion through BeefWeb
2. Deepen graph richness and artist context coverage
3. Improve app-side handling of agent actions
4. Continue separating runtime artifacts from source concerns
