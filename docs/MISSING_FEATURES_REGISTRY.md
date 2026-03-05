# Lyra Oracle Gap Registry

Last audited: March 4, 2026 (updated post cultural intelligence + genre mood sprint)

This file is no longer a wishlist of imagined missing features. It is a registry of real gaps, partials, and connection problems observed in the codebase and current local state.

## Status Legend

- `live` means implemented and connected enough to use
- `partial` means implemented but not fully wired, trusted, or populated
- `missing` means absent in the repo
- `stale-doc` means the docs are wrong, not the code

## Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-001 | Playback ingestion | partial | bridge code exists, `playback_history = 1730` (from taste_backfill, not live BeefWeb) | Run real foobar2000 + BeefWeb session to confirm real-time writes land in DB |
| G-002 | Constellation frontend trust | live | fixture fallback limited to explicit fixture mode | Keep honest, no silent masking |
| G-003 | Constellation layout quality | partial | `ConstellationScene.tsx` uses custom ring layout | Upgrade to force-directed layout (e.g. D3 simulation) |
| G-004 | Text search route wiring | live | text search uses `/api/search` | Keep search semantics consistent |
| G-005 | Desktop agent execution | **live** | `agentActionRouter.ts` maps all known actions to nav/dossier/search; registered in AppShell | Monitor for new action types added backend-side |
| G-006 | Graph richness | partial | connections=8559 but still no sample_lineage edges, influence edges sparse | Run `oracle graph similarity-edges` to add Last.fm similar-artist edges |
| G-007 | Artist shrine depth | partial | shrine endpoint exists but `track_credits=0` limits credit display | `oracle credits enrich` now wired; 6hr schedule will populate incrementally |
| G-008 | Playlist system adoption | partial | `playlist_runs=1`, `playlist_tracks=5` | Use persisted playlist runs more broadly |
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
| G-021 | Spotify history import integrity | **live** | `spotify_history` cleaned from duplicate imports and protected with a dedup guard | Monitor future imports for schema drift only |
| G-022 | Taste profile from real listening history | **live** | `taste_backfill.py` bridges `spotify_history` into `taste_profile`; all 10 dims populated, confidence=1.0 | Improve match quality over time with fuzzy title resolution |
| G-023 | Desktop playback feedback loop | **live** | Desktop audio engine reports playback on track end and skip | Add richer completion / pause / seek telemetry if needed |
| G-024 | Batch acquisition API stability | **live** | Fixed `/api/acquire/batch` worker path | Consider consolidating API batch flow around canonical queue processing |
| G-025 | Pipeline dead-time streamlining | **live** | Removed per-item batch sleep in `smart_pipeline` | Keep profiling acquisition throughput |
| G-026 | Dead acquisition legacy module cleanup | **live** | Archived `oracle/downloader.py` | Watch for forgotten references during future refactors |
| G-027 | Mood language → playlist targeting | **live** | `oracle/mood_interpreter.py` translates mood/genre text into per-act 10-dim targets; wired into `playlust.generate()` | None |
| G-028 | Genre vocabulary in keyword fallback | **live** | ~90 genre/structural tokens added (edm, hardcore, indie, drop, groove etc.); arc modifiers handle "fading into" / "building" / "drops" | Expand token coverage iteratively — LLM handles nuance |
| G-029 | Community track discovery | partial | `oracle/integrations/listenbrainz.py` exists, 24hr scheduler job wired | Has not run yet — will populate `acquisition_queue` with `source='listenbrainz_community'` on first run |
| G-030 | Last.fm similarity graph | partial | `GraphBuilder.build_lastfm_similarity_edges()` exists, 72hr scheduler job wired | Has not run yet — will add `type='similar'` edges to `connections` |
| G-031 | Track credits population | partial | `CreditMapper.map_batch_search()` added, `oracle credits enrich` CLI wired, 6hr scheduler job wired; `track_credits=0` | All 2454 tracks have no `recording_mbid` — will use MB search API at ~1 req/sec; expect weeks to populate fully |
| G-032 | Track structure analysis | partial | `Architect.analyze_structure()` exists (librosa), `oracle structure analyze` CLI wired, 12hr scheduler job wired; `track_structure=0` | 2454 tracks pending — will process 20/run, expect 5+ days to saturate |
| G-033 | Vibe tracks population | partial | `vibe_profiles=4` exist but `vibe_tracks=0` | Run `oracle vibe save --name <name> --query <text>` for each vibe to populate track assignments |
| G-034 | Constellation force-directed layout | missing | Still using ring layout in `ConstellationScene.tsx` | Replace ring layout with D3-force or custom physics simulation |

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
