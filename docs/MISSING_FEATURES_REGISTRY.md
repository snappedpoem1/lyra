# Lyra Oracle Gap Registry

Last audited: March 5, 2026 (post graph + credits pass)

This file tracks active gaps only. Closed items stay in git history and in
`docs/WORKLIST.md`.

## Status Legend

- `live`: implemented and usable
- `partial`: implemented but under-populated, blocked, or not fully trusted
- `missing`: absent from repo
- `blocked-external`: requires live external runtime/session proof

## Active Gap Matrix

| ID | Area | Status | Evidence (current) | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-001 | Playback ingestion proof | blocked-external | `playback_history=30680`, but we still need a clean live foobar2000 + BeefWeb verification pass | Run a controlled live playback session and confirm new rows are clearly live-session attributable |
| G-006 | Graph richness depth | partial | `connections=14137`, `type='similar'=1762`, `type='dimension_affinity'=10560` | Continue staged Last.fm similarity passes to full-library coverage and monitor edge quality |
| G-007 | Artist shrine depth | partial | `track_credits=7` (up from 1) | Continue `oracle credits enrich` in batches until shrine credit surfaces are materially populated |
| G-008 | Playlist system adoption | partial | `playlist_runs=11`, `playlist_tracks=125` | Keep using persisted runs and tune generation quality from real usage feedback |
| G-009 | Spotify export | missing | no active `spotify_export.py` or equivalent export route | Decide ship/no-ship explicitly; implement only if still in-scope |
| G-010 | Runtime/source separation | partial | runtime artifacts still near source root (DB/vector/logs/data) | Decide target runtime-root policy and migrate paths in phases |
| G-029 | Community track discovery | partial | `oracle discover listenbrainz` run returned `0` queued tracks (`source='listenbrainz_community'`) | Inspect ListenBrainz candidate filtering, duplicate checks, and insertion guards |
| G-030 | Last.fm similarity scheduling coverage | partial | feature path works; CLI seeded `similar` edges in staged runs; scheduler interval is 72h; CLI now supports `--workers`, `--request-pause`, `--commit-every` for controlled larger runs | Continue staged/final full run and verify recurring scheduler coverage |
| G-031 | Track credits population rate | partial | MusicBrainz search enrich works but grows slowly (`~1 req/sec`) | Keep scheduled/manual batch enrichment running and monitor fill rate |
| G-032 | Track structure analysis | partial | `track_structure=13`; analyze runs fail with `librosa_not_installed` in current runtime | Install `librosa` in active runtime and resume batch analysis |
| G-033 | Title normalization consolidation | partial | Three independent title-clean implementations: `guard._clean_title()`, `scanner._deep_clean_title()`, `name_cleaner.clean_title()` — pattern sets diverge | Unify into `name_cleaner.py`, add `clean_title_str()` wrapper, update callers |

## Explicitly Not Cancelled

- Spotify-history to local-track fuzzy match quality improvements.
- Playback ingestion live verification with foobar2000 + BeefWeb.
- Graph depth improvements (especially culturally meaningful edges).
- Credit and structure population.
- Runtime/source boundary cleanup.
- Spotify export decision (implement or explicitly close).

## Easy To Hard Execution Order

1. Install `librosa` and verify `oracle structure analyze --limit 50` starts writing rows.
2. Keep `oracle credits enrich` in bounded batches (20-50) and track weekly growth.
3. Continue staged `oracle graph similarity-edges` runs (`--limit-artists` ramp to full).
4. Debug ListenBrainz zero-yield behavior and confirm queue insert path.
5. Improve Spotify history matching normalization/fuzzy fallback and re-run playlist parity checks.
6. Run explicit live BeefWeb verification session with before/after DB evidence.
7. Decide Spotify export scope and runtime-root migration plan.
