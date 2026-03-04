# Lyra Oracle Gap Registry

Last audited: March 4, 2026

This file is no longer a wishlist of imagined missing features. It is a registry of real gaps, partials, and connection problems observed in the codebase and current local state.

## Status Legend

- `live` means implemented and connected enough to use
- `partial` means implemented but not fully wired, trusted, or populated
- `missing` means absent in the repo
- `stale-doc` means the docs are wrong, not the code

## Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-001 | Playback ingestion | partial | bridge code exists, API runtime now attempts autostart, but `playback_history = 0` in current local state | Run a real foobar2000 + BeefWeb session and confirm writes land in DB |
| G-002 | Constellation frontend trust | live | fixture fallback now limited to explicit fixture mode and routes surface backend errors | Keep it honest and avoid reintroducing silent masking |
| G-003 | Constellation layout quality | partial | `ConstellationScene.tsx` uses custom ring layout | Upgrade to a better graph layout if this stays a flagship surface |
| G-004 | Text search route wiring | live | text search now uses the search API instead of vibe generation | Keep search semantics consistent across the product |
| G-005 | Desktop agent execution | partial | command palette now queries `/api/agent/query`, but app-side action execution is still limited | Decide how agent actions should map into desktop navigation or queue operations |
| G-006 | Graph richness | partial | connections exist but memory notes show shallow edge diversity | Add more influence, sample, scene, and collaboration edges |
| G-007 | Artist shrine depth | partial | shrine endpoint exists but depends on enrichment and credits data | Improve enrichment coverage and credit population |
| G-008 | Playlist system adoption | partial | `playlist_runs = 1`, `playlist_tracks = 5` | Use persisted playlist runs more broadly across the product |
| G-009 | Spotify export | missing | no active `spotify_export.py` implementation found | Add export path only if still desired |
| G-010 | Runtime/source separation | partial | repo root contains DB, vector store, logs, downloads, backups | Decide on source-only repo vs all-in-one runtime root |
| G-011 | Source-of-truth docs | stale-doc | old README/roadmap overclaimed or lagged code | Keep docs aligned with code and local state |
| G-012 | Old reference material classification | stale-doc | conversation exports and old prototypes contain mixed historical truth and obsolete plans | Use `docs/REFERENCE_AUDIT.md` and `docs/REFERENCE_INSIGHTS.md` to separate useful references from stale ones |

## Important Connection Gaps

These are more important than missing files because they distort the perceived project state.

### 1. Backend Exists, Desktop Falls Back

The desktop gateway in [`queries.ts`](../desktop/renderer-app/src/services/lyraGateway/queries.ts) still uses fixtures or permissive fallbacks in several places. That is useful for rescue builds and bad for status clarity.

Affected areas:

- constellation
- doctor report
- boot status
- playlists
- queue
- search fallback paths

This should be treated as a product-state gap, not just a UI convenience.

### 2. Search Intent Is Split Across Two Different Behaviors

Evidence:

- `/api/search` and `/api/search/hybrid` exist
- text search now uses `/api/search`
- dimensional search uses direct search

This makes it harder to say what "search" means in the product today.

### 3. Playback Loop Exists in Code but Not in Practice

Evidence:

- `listen` CLI exists
- bridge code exists
- playback endpoints exist
- API runtime now attempts to autostart the listener when BeefWeb is reachable
- `playback_history` remains empty

This is the clearest "implemented but not activated" gap in the whole project.

### 4. Graph Volume Is Better Than Graph Meaning

1,815 connections is enough to support discovery work, but not enough to guarantee culturally useful graph traversal when the edge mix is still narrow.

## Forgotten, Duplicate, or Residual Material

These items are not necessarily broken, but they deserve classification.

### Useful

- [`oracle/graph_builder.py`](../oracle/graph_builder.py)
- [`oracle/enrichers/credit_mapper.py`](../oracle/enrichers/credit_mapper.py)
- [`oracle/playlust.py`](../oracle/playlust.py)
- [`oracle/explain.py`](../oracle/explain.py)
- [`oracle/integrations/beefweb_bridge.py`](../oracle/integrations/beefweb_bridge.py)
- [`docs/specs/SPEC-001_PLAYLIST_SCHEMA.md`](./specs/SPEC-001_PLAYLIST_SCHEMA.md)
- [`docs/specs/SPEC-002_PLAYLIST_LOGIC.md`](./specs/SPEC-002_PLAYLIST_LOGIC.md)

### Needs Classification Or Cleanup

- `Lyra_Oracle_System`
- large runtime artifacts in repo root
- duplicated historical plans in docs and external reference material
- legacy prototype material from earlier project workspaces

## Recommended Order Of Work

1. Verify playback logging with a live BeefWeb session.
2. Decide whether command-palette agent actions should execute app-side behavior.
3. Improve graph depth and artist context coverage.
4. Classify or archive residual duplicate material.
5. Keep this registry current whenever a gap is closed.
