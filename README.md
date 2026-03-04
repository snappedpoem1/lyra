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
```

Run the desktop renderer:

```powershell
cd desktop\renderer-app
npm install
npm run dev
```

## Key Docs

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
