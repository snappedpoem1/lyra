# Lyra Oracle: Current State And Direction

Last audited: March 4, 2026

This document is the current high-level status view of Lyra Oracle.
It describes what exists in the repo now, what is still partial, and what the next practical steps are.

## Executive Summary

Lyra Oracle is already a substantial local music system.
It is not a prototype, and it is not a finished product either.

The current shape is:

- a strong Python backend
- a real local data model
- working search, scoring, playlist, enrichment, and discovery subsystems
- a desktop app with several live feature paths
- a smaller set of remaining runtime and integration gaps

Current audited counts:

| Metric | Value |
| --- | ---: |
| tracks | 2,454 |
| track_scores | 2,454 |
| embeddings | 2,454 |
| artists | 950 |
| connections | 1,815 |
| vibe_profiles | 4 |
| playlist_runs | 1 |
| playlist_tracks | 5 |
| acquisition_queue | 23,216 |
| playback_history | 0 |

## Implemented

### Core Library Intelligence

- library scan and indexing
- CLAP embeddings
- semantic and hybrid search
- 10-dimensional scoring
- library status and diagnostics

Main code:

- [`oracle/scanner.py`](../oracle/scanner.py)
- [`oracle/indexer.py`](../oracle/indexer.py)
- [`oracle/search.py`](../oracle/search.py)
- [`oracle/scorer.py`](../oracle/scorer.py)
- [`oracle/cli.py`](../oracle/cli.py)

### Playlists, Vibes, And Explainability

- persisted vibe and playlist run storage
- saved reasons and explainability
- 4-act Playlust generation

Main code:

- [`oracle/db/schema.py`](../oracle/db/schema.py)
- [`oracle/types.py`](../oracle/types.py)
- [`oracle/vibes.py`](../oracle/vibes.py)
- [`oracle/explain.py`](../oracle/explain.py)
- [`oracle/playlust.py`](../oracle/playlust.py)
- [`oracle/api/blueprints/vibes.py`](../oracle/api/blueprints/vibes.py)
- [`oracle/api/blueprints/discovery.py`](../oracle/api/blueprints/discovery.py)

### Enrichment And Artist Context

- biographer
- credit mapper
- artist shrine endpoint
- taste profile endpoint

Main code:

- [`oracle/enrichers/biographer.py`](../oracle/enrichers/biographer.py)
- [`oracle/enrichers/credit_mapper.py`](../oracle/enrichers/credit_mapper.py)
- [`oracle/api/blueprints/enrich.py`](../oracle/api/blueprints/enrich.py)
- [`oracle/api/blueprints/radio.py`](../oracle/api/blueprints/radio.py)

### Discovery And Oracle Layer

- scout, lore, DNA, architect, and radio modules
- deep-cut discovery
- oracle discovery
- graph building

Main code:

- [`oracle/scout.py`](../oracle/scout.py)
- [`oracle/lore.py`](../oracle/lore.py)
- [`oracle/dna.py`](../oracle/dna.py)
- [`oracle/architect.py`](../oracle/architect.py)
- [`oracle/radio.py`](../oracle/radio.py)
- [`oracle/deepcut.py`](../oracle/deepcut.py)
- [`oracle/graph_builder.py`](../oracle/graph_builder.py)
- [`oracle/api/blueprints/discovery.py`](../oracle/api/blueprints/discovery.py)

### Playback Bridge And Feedback Loop Code

- BeefWeb bridge code
- listen endpoints
- CLI listener command
- API runtime autostart attempt when BeefWeb is reachable

Main code:

- [`oracle/integrations/beefweb_bridge.py`](../oracle/integrations/beefweb_bridge.py)
- [`oracle/api/blueprints/discovery.py`](../oracle/api/blueprints/discovery.py)
- [`oracle/api/__init__.py`](../oracle/api/__init__.py)
- [`oracle/cli.py`](../oracle/cli.py)

### Desktop App

- React/Vite renderer
- playlist, library, oracle, queue, search, and artist routes
- shrine and constellation query paths
- text search wired to the real search API
- command palette wired to the live agent backend
- fixture mode reserved for explicit fixture use rather than silent fallback

Main code:

- [`desktop/renderer-app/src/app/routes`](../desktop/renderer-app/src/app/routes)
- [`desktop/renderer-app/src/services/lyraGateway/queries.ts`](../desktop/renderer-app/src/services/lyraGateway/queries.ts)
- [`desktop/renderer-app/src/features`](../desktop/renderer-app/src/features)

## Partial

### Playback Learning Needs Live Verification

Evidence:

- bridge code exists
- listener can autostart from API runtime
- listen endpoints exist
- `playback_history` is still empty in the current local state

Implication:

- the playback loop is implemented
- it still needs a real player session to prove writes and taste feedback are happening

### Agent UI Is Connected But Still Shallow

Evidence:

- command palette now calls the backend agent endpoint
- agent replies are shown in the desktop UI
- app-side action execution is still minimal

Implication:

- the agent is no longer stubbed
- the surrounding interaction model still needs deeper integration

### Constellation Is Live But Not Final

Evidence:

- constellation backend exists
- the desktop now surfaces backend errors instead of silently swapping to fixtures
- the current visualization still uses a custom static layout

Implication:

- constellation is a real live surface now
- it is not yet the final form of the flagship graph view

### Connection Graph Quality Is Still Thin

Evidence:

- 1,815 total connections
- graph richness still needs more influence, scene, and collaboration depth

Implication:

- graph volume is useful
- graph diversity still needs work

## Missing

### Spotify Playlist Export

There is no finished repo implementation for exporting playlists back out to Spotify.

### Cleaner Runtime Separation

The repo still mixes source, database, vector store, logs, downloads, backups, and caches more than it should long-term.

## Reference Policy

Historical material informed the project direction, but it is not the source of truth for current status.

Use this order of trust:

1. repo code
2. current local data
3. current memory files
4. current docs
5. historical references

## Recommended Next Steps

1. Verify playback ingestion with a real foobar2000 + BeefWeb session.
2. Deepen graph edge types and artist context coverage.
3. Improve app-side handling of agent actions.
4. Continue separating runtime artifacts from source concerns.
