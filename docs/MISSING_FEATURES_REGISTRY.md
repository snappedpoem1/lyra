# Lyra Oracle Gap Registry

Last audited: March 4, 2026 (updated post UI sprint)

This file is no longer a wishlist of imagined missing features. It is a registry of real gaps, partials, and connection problems observed in the codebase and current local state.

## Status Legend

- `live` means implemented and connected enough to use
- `partial` means implemented but not fully wired, trusted, or populated
- `missing` means absent in the repo
- `stale-doc` means the docs are wrong, not the code

## Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-001 | Playback ingestion | partial | bridge code exists, API runtime now attempts autostart, but `playback_history = 0` | Run a real foobar2000 + BeefWeb session and confirm writes land in DB |
| G-002 | Constellation frontend trust | live | fixture fallback limited to explicit fixture mode | Keep honest, no silent masking |
| G-003 | Constellation layout quality | partial | `ConstellationScene.tsx` uses custom ring layout | Upgrade to force-directed layout (e.g. D3 simulation) |
| G-004 | Text search route wiring | live | text search uses `/api/search` | Keep search semantics consistent |
| G-005 | Desktop agent execution | **live** | `agentActionRouter.ts` maps all known actions to nav/dossier/search; registered in AppShell | Monitor for new action types added backend-side |
| G-006 | Graph richness | partial | connections exist but edge diversity is shallow | Add influence, sample, scene, collaboration edges |
| G-007 | Artist shrine depth | partial | shrine endpoint exists but coverage depends on enrichment runs | Improve enrichment coverage, credit population |
| G-008 | Playlist system adoption | partial | `playlist_runs = 1`, `playlist_tracks = 5` | Use persisted playlist runs more broadly |
| G-009 | Spotify export | missing | no active `spotify_export.py` | Add export only if still desired |
| G-010 | Runtime/source separation | partial | repo root contains DB, vector store, logs | Decide on source-only vs all-in-one root |
| G-011 | Source-of-truth docs | stale-doc | old README/roadmap overclaimed | Keep docs aligned with code and local state |
| G-012 | Old reference material classification | stale-doc | conversation exports and old prototypes mixed | Use `docs/REFERENCE_AUDIT.md` to separate |
| G-013 | Keyboard navigation | **live** | Space/J/K/M/←/→/Esc/Ctrl+K/Slash all wired in AppShell | None |
| G-014 | Context menus on track rows | **live** | Right-click on library tracks and queue rows — Play, Queue, Info, Artist, Copy path | Extend to playlist track table if needed |
| G-015 | Queue drag-to-reorder | **live** | HTML5 DnD with drag handles in `QueueLane.tsx`, `moveItem` wired | None |
| G-016 | Playlist card mosaic | **live** | `PlaylistMosaic` component, `PlaylistGrid` card layout, `PlaylistHero` uses it | Consider fetching real cover art when available |
| G-017 | Playback position persistence | **live** | `beforeunload` snapshots `currentTime`; `audioEngine.loadTrack` restores on session resume | None |
| G-018 | Transport dock waveform | **live** | Canvas RAF renderer (32 bars) in `BottomTransportDock`, reads `audioAnalyzer` frame data | None |
| G-019 | Settings form styling | **live** | Proper field/label/checkbox/hint markup with `.settings-*` CSS classes | None |
| G-020 | Command palette arrow nav | **live** | Up/Down keys, `is-active` highlight, Enter runs highlighted command, 14 static commands | None |
| G-021 | Spotify history import integrity | **live** | `spotify_history` cleaned from duplicate imports and protected with a dedup guard (`UNIQUE INDEX` + `INSERT OR IGNORE`) | Monitor future imports for schema drift only |
| G-022 | Taste profile from real listening history | **live** | `oracle/taste_backfill.py` bridges `spotify_history` into `taste_profile`; 1,730 matched local tracks written as real taste signals | Improve match quality over time with normalized/fuzzy title resolution |
| G-023 | Desktop playback feedback loop | **live** | Desktop audio engine now reports playback on track end and track switch/skip so Lyra learns from in-app listening | Add richer completion / pause / seek telemetry if needed |
| G-024 | Batch acquisition API stability | **live** | Fixed broken `/api/acquire/batch` worker path by removing bad `fast_batch` imports and correcting `_download_one(...)` call shape | Consider consolidating API batch flow more tightly around canonical queue processing later |
| G-025 | Pipeline dead-time streamlining | **live** | Removed per-item batch sleep in `smart_pipeline`, reduced startup wait, reduced Real-Debrid poll interval | Keep profiling acquisition throughput before changing retry/backoff behavior further |
| G-026 | Dead acquisition legacy module cleanup | **live** | Archived unused `oracle/downloader.py`; active acquisition paths remain `waterfall.py`, `smart_pipeline.py`, and queue/API entrypoints | Watch for any forgotten references during future refactors |

### March 2026 status correction

Lyra is no longer in a true playback/taste cold-start state.
The biggest change in this cycle is that Spotify extended streaming history is now being used as real behavioral input instead of sitting adjacent to the system as unused archive data.

## Important Connection Gaps

These are more important than missing files because they distort the perceived project state.

### 1. Backend Exists, Desktop Falls Back

The desktop gateway in [`queries.ts`](../desktop/renderer-app/src/services/lyraGateway/queries.ts) still uses fixtures or permissive fallbacks in several places.

Affected areas:

- constellation
- doctor report
- boot status
- playlists
- queue
- search fallback paths

### 2. Search Intent Is Split Across Two Different Behaviors

- `/api/search` and `/api/search/hybrid` exist
- text search uses `/api/search`
- dimensional search uses direct search

This makes it harder to say what "search" means in the product today.

### 3. Playback Loop Exists in Code but Not in Practice

- `listen` CLI exists, bridge code exists, playback endpoints exist
- API runtime now attempts autostart
- `playback_history` remains empty

This is the clearest "implemented but not activated" gap in the whole project.

### 4. Graph Volume Is Better Than Graph Meaning

1,815 connections is enough to support discovery work, but not enough to guarantee culturally useful graph traversal when the edge mix is still narrow.

## Forgotten, Duplicate, or Residual Material

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

1. Verify playback logging with a live BeefWeb session (G-001, G-003).
2. Improve graph depth and artist context coverage (G-006, G-007).
3. Upgrade constellation to force-directed layout (G-003).
4. Classify or archive residual duplicate material (G-012).
5. Keep this registry current whenever a gap is closed.
