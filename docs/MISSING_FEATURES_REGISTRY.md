# Lyra Oracle Gap Registry

Last audited: March 6, 2026

This file tracks active gaps only.
Closed items stay in git history and session logs.

## Status Legend

- `live`: implemented and usable
- `partial`: implemented but not fully validated/populated
- `missing`: absent
- `blocked-external`: depends on external runtime/session proof

## Active Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-039 | Docker elimination / packaged runtime | partial | core app no longer requires Docker, legacy-service bootstrap is opt-in only, and bundled acquisition-runtime builders now exist; remaining gap is packaged installer proof on a clean machine | Validate packaged installer/runtime on a clean machine, continue internalizing acquisition capabilities, and keep Docker as optional legacy layer only |
| G-009 | Spotify export | missing | no active export route/module | Explicitly decide ship vs cancel; implement only if in scope |
| G-010 | Runtime/source separation | partial | packaged sidecar and bundled helper executables now stage under dedicated `.lyra-build/bin`, but broader runtime/generated artifact separation is still incomplete | Continue migrating generated/runtime outputs behind explicit build/runtime roots and verify installer behavior |
| G-030 | Similarity coverage depth | partial | staged `similar` edge growth exists but incomplete full-library coverage | Continue bounded similarity runs and quality checks |
| G-031 | Credit enrichment depth | partial | credit population is still low | Continue bounded `oracle credits enrich` runs |
| G-032 | Structure analysis coverage | partial | structure table grows but incomplete coverage | Continue bounded analyze runs and harden difficult-file handling |
| G-034 | Streamrip runtime availability | partial | standalone bundled `rip.exe` now builds and is detected by doctor/status, but a full packaged tier-2 acquisition proof is still pending | Validate one successful packaged/runtime-backed tier-2 acquisition |
| G-035 | Tauri sidecar packaging completeness | partial | packaged runtime build now stages `lyra_backend.exe` plus bundled acquisition helpers, but clean-machine installer proof is still pending | Verify bundled `lyra_backend.exe` and runtime-tool behavior on a clean machine installer run |
| G-036 | Native audio production confidence | partial | `miniaudio` path exists with fallback but soak matrix not complete | Validate long-session/device reliability, pause/seek/repeat/resume behavior |
| G-037 | Oracle action breadth | partial | action router now executes `queue_tracks`, `start_vibe`, `start_playlust`, `switch_chaos_intensity`, and `request_acquisition`; unified shell exposes keep/queue/play/skip and acquisition lead actions, but broader oracle execution depth is still expandable | Continue broadening high-leverage oracle actions after installer + soak proof |
| G-038 | Recommendation feedback loop | live | brokered recommendations now persist accept/queue/skip/replay/acquire-request outcomes and apply that data as a ranking bias | Expand feedback sophistication later if passive playback-derived reinforcement is needed |

## Explicitly Not Cancelled

- Spotify-history-to-local-track matching quality improvements
- Graph richness improvements
- Credits and structure depth work
- Runtime/source separation cleanup
- Sidecar packaging hardening
- Oracle action depth expansion

## Execution Order (Easy -> Hard)

1. Complete clean-machine installer verification for bundled sidecar + acquisition tools.
2. Complete native audio soak and restart recovery validation.
3. Validate one successful packaged/runtime-backed streamrip acquisition.
4. Continue graph/credits/structure coverage work.
5. Resolve Spotify export scope decision.
