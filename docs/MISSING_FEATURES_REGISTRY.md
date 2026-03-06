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
| G-009 | Spotify export | missing | no active export route/module | Explicitly decide ship vs cancel; implement only if in scope |
| G-010 | Runtime/source separation | partial | runtime artifacts still near source root | Define runtime root policy and migrate in phases |
| G-030 | Similarity coverage depth | partial | staged `similar` edge growth exists but incomplete full-library coverage | Continue bounded similarity runs and quality checks |
| G-031 | Credit enrichment depth | partial | credit population is still low | Continue bounded `oracle credits enrich` runs |
| G-032 | Structure analysis coverage | partial | structure table grows but incomplete coverage | Continue bounded analyze runs and harden difficult-file handling |
| G-034 | Streamrip runtime availability | partial | tier-2 adapter exists, host `rip` CLI still unavailable | Install/configure `rip` and validate tier-2 acquisition |
| G-035 | Tauri sidecar packaging completeness | partial | sidecar build and debug bundling are now validated locally, but clean-machine installer proof is still pending | Verify bundled `lyra_backend.exe` behavior on a clean machine installer run |
| G-036 | Native audio production confidence | partial | `miniaudio` path exists with fallback but soak matrix not complete | Validate long-session/device reliability, pause/seek/repeat/resume behavior |
| G-037 | Oracle action breadth | partial | action router executes `queue_tracks`, `start_vibe`, `start_playlust`, and `switch_chaos_intensity`; unified shell now exposes vibe/playlust launchers + queue action feedback, but chaos intensity remains fixed and action telemetry is still shallow | Add explicit chaos intensity presets and richer per-action result telemetry/UX |

## Explicitly Not Cancelled

- Spotify-history-to-local-track matching quality improvements
- Graph richness improvements
- Credits and structure depth work
- Runtime/source separation cleanup
- Sidecar packaging hardening
- Oracle action depth expansion

## Execution Order (Easy -> Hard)

1. Install/configure streamrip (`rip`) and validate tier-2 acquisition.
2. Complete sidecar build-and-bundle and clean-machine installer verification.
3. Complete native audio soak and restart recovery validation.
4. Expand oracle action execution breadth.
5. Continue graph/credits/structure coverage work.
6. Resolve Spotify export scope decision.
