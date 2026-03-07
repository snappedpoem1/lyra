# Lyra Oracle Gap Registry

Last audited: March 6, 2026

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
| G-039 | Docker elimination / packaged runtime | partial | core app no longer requires Docker, legacy-service bootstrap is opt-in only, bundled acquisition-runtime builders exist, clean-machine artifact proof passes locally, debug packaged-host boot reaches healthy backend state, installed-layout validation passes locally, and live Qobuz acquisition via bundled `rip.exe` is confirmed; remaining gap is true blank-machine installer validation | Install the Lyra installer EXE on a clean Windows VM and confirm first launch works |
| G-009 | Spotify export | missing | no active export route or module | Explicitly decide ship vs cancel; implement only if in scope |
| G-010 | Runtime/source separation | partial | packaged sidecar and bundled helper executables stage under dedicated `.lyra-build/bin`, but broader runtime/generated artifact separation is still incomplete | Continue migrating generated and runtime outputs behind explicit build/runtime roots and verify installer behavior |
| G-030 | Similarity coverage depth | partial | staged `similar` edge growth exists but incomplete full-library coverage | Continue bounded similarity runs and quality checks |
| G-031 | Credit enrichment depth | partial | credit population is still low | Continue bounded `oracle credits enrich` runs |
| G-032 | Structure analysis coverage | partial | structure table grows but incomplete coverage | Continue bounded analyze runs and harden difficult-file handling |
| G-034 | Streamrip runtime availability | live | bundled `rip.exe` resolves correctly, streamrip 2.x command syntax is fixed, static proof passes, and `validate_packaged_streamrip.ps1 -LiveAcquire` succeeded against Qobuz | Closed |
| G-035 | Tauri sidecar packaging completeness | partial | clean-machine artifact proof passes, simulated install layout proof passes, installed-layout validation passes against rebuilt host, frozen runtime roots are hardened, packaged runtime-root resolution now handles installed layouts more defensibly, the frozen sidecar now explicitly bundles `oracle.api.blueprints.*`, and packaged smoke now claims a fresh backend instead of reusing an existing listener; remaining gap is a true blank-machine install and first launch | Install the Lyra installer EXE on a clean Windows VM and confirm first launch works |
| G-036 | Native audio production confidence | partial | `miniaudio` path exists with fallback, parity hardening now performs restart recovery plus mutating soak checkpoints/logging, and the short local mutation run passes; the full long-session matrix is still incomplete | Validate a full 4-hour soak plus real-device pause/seek/repeat/resume reliability |
| G-037 | Oracle action breadth | partial | action router executes `queue_tracks`, `start_vibe`, `start_playlust`, `switch_chaos_intensity`, and `request_acquisition`; unified shell exposes keep/queue/play/skip and acquisition lead actions, but broader oracle execution depth is still expandable | Continue broadening high-leverage Oracle actions after installer and soak proof |
| G-038 | Recommendation feedback loop | live | brokered recommendations persist accept/queue/skip/replay/acquire-request outcomes and apply that data as a ranking bias | Expand feedback sophistication later if passive playback-derived reinforcement is needed |

## Explicitly Not Cancelled

- Spotify-history-to-local-track matching quality improvements
- Graph richness improvements
- Credits and structure depth work
- Runtime/source separation cleanup
- Sidecar packaging hardening
- Oracle action depth expansion

## Execution Order (Easy -> Hard)

1. Complete blank-machine installer verification for bundled sidecar and acquisition tools.
2. Complete native audio soak and restart recovery validation.
3. Continue graph, credits, and structure coverage work.
4. Resolve Spotify export scope decision.
