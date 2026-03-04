# CLAUDE.md - Current Lyra Oracle Agent Context

Last updated: March 4, 2026

This file is the current entry point for agent-side project context.

## Read First

1. `.claude/REFERENCE_INDEX.md`
2. `.claude/memory/MEMORY.md`
3. `.claude/memory/SESSIONS.md`
4. `docs/MASTER_PLAN_EXPANDED.md`
5. `docs/MISSING_FEATURES_REGISTRY.md`
6. `docs/REFERENCE_INSIGHTS.md`

## What Lyra Is

Lyra Oracle is a local-first music intelligence system built around:

- a Python CLI and Flask API
- SQLite for structured state
- Chroma-backed semantic search
- 10-dimensional emotional scoring
- local library ownership, playlist reasoning, discovery, and acquisition tooling
- a desktop UI that is mostly live, with selective fixture support reserved for explicit development modes

It is not a generic dashboard app. It is a music system with real local files, real metadata ambiguity, and a strong distinction between implemented modules and fully connected user-facing surfaces.

## Current Truth

Audited against the repo and current local database on March 4, 2026:

- `tracks=2454`
- `track_scores=2454`
- `embeddings=2454`
- `connections=1815`
- `vibe_profiles=4`
- `playlist_runs=1`
- `playlist_tracks=5`
- `playback_history=0`
- `acquisition_queue=23216`

Implemented in code:

- search and hybrid search
- vibes and persisted playlist records
- playlust and explainability
- biographer, graph builder, credit mapper
- deep-cut and oracle discovery pipelines
- listen status and BeefWeb bridge code
- constellation backend and artist shrine backend

Still partial in practice:

- playback ingestion is not active in the local state
- command palette actions are still shallow even though the backend path is now wired
- constellation is live but still uses a simple custom layout
- graph richness is not yet deep enough for the full cultural-oracle vision
- runtime artifacts still live too close to source and should be separated more clearly

## Working Rules

- Trust code and local data over old docs.
- Do not write docs that claim a feature is missing without checking the repo first.
- Do not write docs that claim a feature is complete if the surface is only partially wired.
- Prefer repo-relative references in docs unless an absolute path is genuinely necessary.
- Treat exported conversations, old planning notes, and prototype folders as historical inputs, not live truth.

## Session Close

When work materially changes the project state:

- update `.claude/memory/MEMORY.md`
- append the change to `.claude/memory/SESSIONS.md`
- update `docs/MISSING_FEATURES_REGISTRY.md` if a real gap was closed or newly identified
