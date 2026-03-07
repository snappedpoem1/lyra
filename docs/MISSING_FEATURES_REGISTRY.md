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
| G-039 | Docker elimination / packaged runtime | blocked-external | core app no longer requires Docker, legacy-service bootstrap is opt-in only, bundled acquisition-runtime builders exist, clean-machine artifact proof passes locally, debug packaged-host boot reaches healthy backend state, installed-layout validation passes locally, and live Qobuz acquisition via bundled `rip.exe` is confirmed; remaining gap is true blank-machine installer validation, but no clean Windows machine or VM is currently available for that proof | Acquire a clean Windows machine or VM and confirm first launch from the Lyra installer EXE |
| G-009 | Spotify export | cancelled | Spotify is auxiliary to local-first library; no export route is needed in the current product direction. Spotify import history is already ingested for recommendation bias. Export is out of scope. | Closed — cancelled per product direction |
| G-030 | Similarity coverage depth | partial | staged `similar` edge growth exists but incomplete full-library coverage; current `similar` edge count is 1,762 and a bounded 40-artist Last.fm pass added no new local-target edges | Continue bounded similarity runs and quality checks |
| G-031 | Credit enrichment depth | partial | credit population is still low (`48` total credit rows); Wave 10 MBID identity spine is now landed — `CreditMapper.map_batch()` column bug fixed (`musicbrainz_id` → `recording_mbid`), batch MBID resolver running; once recording_mbid population reaches >50% credits will be available via MBID-direct lookup | Run `oracle mbid resolve --limit 2000` to completion, then `oracle credits enrich --limit 500` for MBID-backed credits |
| G-032 | Structure analysis coverage | partial | structure table continues to grow; latest bounded run increased analyzed tracks from `159` to `172` while difficult-file warnings still fall back through librosa/audioread | Continue bounded analyze runs and harden difficult-file handling |
| G-034 | Streamrip runtime availability | live | bundled `rip.exe` resolves correctly, streamrip 2.x command syntax is fixed, static proof passes, and `validate_packaged_streamrip.ps1 -LiveAcquire` succeeded against Qobuz | Closed |
| G-035 | Tauri sidecar packaging completeness | blocked-external | clean-machine artifact proof passes, simulated install layout proof passes, installed-layout validation passes against the rebuilt Tauri 2 host, frozen runtime roots are hardened, packaged runtime-root resolution now handles installed layouts more defensibly, the frozen sidecar now explicitly bundles `oracle.api.blueprints.*`, and packaged smoke now claims a fresh backend instead of reusing an existing listener; remaining gap is a true blank-machine install and first launch after the runtime/data-root contract settles, but that proof is blocked without a clean Windows machine or VM | Run the blank-machine installer proof against the finalized packaged/runtime contract once a clean Windows machine or VM is available |
| G-036 | Native audio production confidence | partial | `miniaudio` path exists with fallback, parity hardening now performs restart recovery plus mutating soak checkpoints/logging, the 60-second parity soak passes with the rebuilt Wave 5+6 sidecar (pause/resume and seek mutations, restart recovery), and Wave 4 host modernization stayed green on Tauri 2; dev data root is now fully migrated so the `-UseLegacyDataRoot` workaround is no longer required for dev-mode soak validation; the full 4-hour long-session matrix is still deferred | Reopen the release-gate lane and validate a full 4-hour soak plus real-device pause/seek/repeat/resume reliability |
| G-037 | Oracle action breadth | **closed** | Wave 12: 17 execute action types now wired (`queue_tracks`, `start_vibe`, `start_playlust`, `switch_chaos_intensity`, `request_acquisition`, `resume`, `set_volume`, `set_shuffle`, `set_repeat`, `clear_queue`, `play_artist`, `play_album`, `play_similar` + `play`/`pause`/`next`/`previous`); agentActionRouter extended accordingly; 11 new contract tests; closed S-20260307-14 |
| G-038 | Recommendation feedback loop | live | brokered recommendations persist accept/queue/skip/replay/acquire-request outcomes and apply that data as a ranking bias | Expand feedback sophistication later if passive playback-derived reinforcement is needed |

## Explicitly Not Cancelled

- Spotify-history-to-local-track matching quality improvements
- Graph richness improvements
- Credits and structure depth work
- Runtime/source separation cleanup
- Sidecar packaging hardening
- Oracle action depth expansion

## Execution Order (Easy -> Hard)

1. Continue graph, credits, and structure coverage work.
2. Resolve Spotify export scope decision.
3. Resume blank-machine installer verification when a clean Windows machine or VM exists.
4. Reopen native audio soak validation when the release-gate lane is back in scope.
