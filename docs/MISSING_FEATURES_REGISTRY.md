# Lyra Oracle Gap Registry

Last audited: March 7, 2026

This file tracks active gaps only.
Closed items stay in git history and session logs.

## Status Legend

- `live`: implemented and usable
- `partial`: implemented but not fully validated or populated
- `missing`: absent
- `blocked-external`: depends on external runtime or session proof

## Active Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-039 | Docker elimination / packaged runtime | blocked-external | Core app no longer requires Docker, legacy-service bootstrap is opt-in only, bundled acquisition-runtime builders exist, clean-machine artifact proof passes locally, debug packaged-host boot reaches a healthy backend state, installed-layout validation passes locally, and live Qobuz acquisition via bundled `rip.exe` is confirmed; remaining gap is true blank-machine installer validation, but no clean Windows machine or VM is currently available for that proof | Acquire a clean Windows machine or VM and confirm first launch from the Lyra installer EXE |
| G-030 | Similarity coverage depth | partial | Staged `similar` edge growth exists but incomplete full-library coverage; current `similar` edge count is 1,762 and a bounded 40-artist Last.fm pass added no new local-target edges | Continue bounded similarity runs and quality checks |
| G-031 | Credit enrichment depth | partial | Credit population is still low (`48` total credit rows); Wave 10 MBID identity spine is now landed, `CreditMapper.map_batch()` uses `recording_mbid`, and the batch MBID resolver is running; once recording MBID population reaches a practical threshold, credits will be available via MBID-direct lookup | Run `oracle mbid resolve --limit 2000` to completion, then `oracle credits enrich --limit 500` for MBID-backed credits |
| G-032 | Structure analysis coverage | partial | Structure table continues to grow; latest bounded run increased analyzed tracks from `159` to `172` while difficult-file warnings still fall back through librosa/audioread | Continue bounded analyze runs and harden difficult-file handling |
| G-034 | Streamrip runtime availability | live | Bundled `rip.exe` resolves correctly, streamrip 2.x command syntax is fixed, static proof passes, and `validate_packaged_streamrip.ps1 -LiveAcquire` succeeded against Qobuz | Expand only if future provider/runtime regressions appear |
| G-035 | Tauri sidecar packaging completeness | blocked-external | Clean-machine artifact proof passes, simulated install layout proof passes, installed-layout validation passes against the rebuilt Tauri 2 host, frozen runtime roots are hardened, packaged runtime-root resolution now handles installed layouts more defensibly, the frozen sidecar explicitly bundles `oracle.api.blueprints.*`, and packaged smoke claims a fresh backend instead of reusing an existing listener; remaining gap is a true blank-machine install and first launch after the runtime/data-root contract settles, but that proof is blocked without a clean Windows machine or VM | Run the blank-machine installer proof against the finalized packaged/runtime contract once a clean Windows machine or VM is available |
| G-036 | Native audio production confidence | partial | `miniaudio` path exists with fallback, parity hardening performs restart recovery plus mutating soak checkpoints/logging, bounded parity runs pass, and Wave 4 host modernization stayed green on Tauri 2; the full 4-hour long-session matrix is still deferred | Reopen the release-gate lane and validate a full 4-hour soak plus real-device pause/seek/repeat/resume reliability |
| G-038 | Recommendation feedback loop | live | Brokered recommendations persist accept/queue/skip/replay/acquire-request outcomes and apply that data as a ranking bias | Expand feedback sophistication later if passive playback-derived reinforcement is needed |

## Closed Or Cancelled (Reference Only)

- `G-009` Spotify export
  Cancelled. Spotify export is out of scope for the current local-first product direction.
- `G-037` Oracle action breadth
  Closed in Wave 12.
- `G-040` Named playlist intelligence
  Closed in Wave 13.
- `G-041` Saved playlist UI surface
  Closed in Wave 14.
- `G-042` Biographer stats `UnboundLocalError`
  Closed in Wave 15 (S-20260307-21). Fixed import scope in `oracle/cli.py`.
- `G-043` Revelations metric endpoint
  Closed in Wave 15 (S-20260307-21). `GET /api/stats/revelations` added to `core.py`; returns count_this_window, count_all_time, and detail list.
- `G-044` Duplicate detection module
  Closed in Wave 15 (S-20260307-21). `oracle/duplicates.py` created with exact-hash, metadata-fuzzy, and path strategies. API at `GET /api/duplicates` and `GET /api/duplicates/summary`.
- `G-045` Vibe → saved_playlists orphan
  Closed in Wave 15 (S-20260307-21). `save_vibe()` in `oracle/vibes.py` now mirrors every vibe save into `saved_playlists` + `saved_playlist_tracks` using a deterministic UUID5 so re-saves are idempotent.

## Explicitly Not Cancelled

- Spotify-history-to-local-track matching quality improvements
- Graph richness improvements
- Credits and structure depth work
- Runtime/source separation cleanup
- Sidecar packaging hardening
- Oracle action depth expansion

## Execution Order (Easy -> Hard)

1. Continue graph, credits, and structure coverage work.
2. Resume blank-machine installer verification when a clean Windows machine or VM exists.
3. Reopen native audio soak validation when the release-gate lane is back in scope.
