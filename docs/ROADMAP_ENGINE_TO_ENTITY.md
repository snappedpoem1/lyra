# Lyra: Engine to Entity - Unified Master Plan

Last updated: March 6, 2026

This file is the single forward-plan authority for Lyra.
It merges the original Engine-to-Entity vision with the Unified App Cutover execution track.

## 1) Mission Lock

Lyra is a local-first music entity: one app entrypoint for playback, library, queue, oracle actions, and acquisition control surfaces.

Core priority:

- Listening experience first.
- Backend expansion only when it ships visible user value in the same or next phase.

## 2) Decision Lock

1. Tauri is the only supported desktop host path.
2. Backend player is canonical playback authority.
3. Browser `HTMLAudio` is non-canonical runtime behavior.
4. Unified modular workspace shell is the active UI runtime.
5. Docker is optional acquisition support, not required for daily local playback.
6. Ambient oracle behavior is default when oracle action layer is enabled.
7. Docker is a legacy compatibility layer only; packaged/bundled runtime capabilities take priority over containerized dependencies.

## 3) Current Accomplishment

### Host and runtime

- Tauri shell scaffold exists and builds.
- Desktop boot scripts route to Tauri-first flow.
- Tray/media controls route to backend player commands.

### Canonical player backend

- `oracle/player/*` domain implemented with persisted `player_state` and `player_queue`.
- Canonical API contract implemented:
  - `GET /api/player/state`
  - `GET /api/player/queue`
  - `POST /api/player/play`
  - `POST /api/player/pause`
  - `POST /api/player/seek`
  - `POST /api/player/next`
  - `POST /api/player/previous`
  - `POST /api/player/queue/add`
  - `POST /api/player/queue/reorder`
  - `POST /api/player/mode`
- `/ws/player` event stream implemented as SSE.
- `/api/playback/record` kept as compatibility-only, non-canonical path.

### Unified frontend shell

- Active runtime replaced with one modular workspace shell:
  - Library pane
  - Now Playing pane
  - Queue pane
  - Collapsible Oracle pane
- Player state is hydrated from backend snapshots plus SSE stream updates.

### Oracle action contract

- `POST /api/oracle/chat`
- `POST /api/oracle/action/execute`
- `GET /api/oracle/context`

### Recommendation orchestration

- `POST /api/recommendations/oracle` broker implemented.
- Broker fuses local radio, Last.fm similar-track signals, and ListenBrainz community popularity.
- Unified Oracle surface now exposes:
  - novelty bands
  - provider weighting
  - explicit chaos presets
  - explainable recommendation provenance
  - acquisition radar leads

## 4) Program State

Lyra is entering a split modernization sequence.

Rule:

- no build/runtime/product modernization proceeds until the document and agent-hardening wave lands
- roadmap, state, worklist, registry, and scoped agent instructions must agree before later implementation waves begin

This sequence intentionally fronts governance first so parallel agents do not drift, collide, or implement against stale repo truth.

## 5) Open Gaps

1. Runtime/data-root authority is still incomplete:
   - generated paths are improved through `.lyra-build`
   - repo-root mutable data assumptions still remain
   - `LYRA_DATA_ROOT` cutover is not implemented yet
2. Native audio production validation (`miniaudio`) on real devices/long sessions is still pending.
3. Packaged sidecar certainty (`lyra_backend.exe`) on a true blank-machine installer is still pending.
4. Oracle action breadth, metadata depth, and product explainability are still expandable after governance and build/runtime foundations are aligned.

## 6) Wave Plan

### Wave 1 - Document and Agent Hardening (landed locally)

Gate:
- authoritative docs, lane briefs, and scoped agent instructions all agree on execution order before any later modernization wave begins

Deliverables:
- roadmap/state/worklist/registry alignment
- README truth cleanup
- root plus scoped agent instruction surfaces
- explicit parallel lane briefs for later waves

### Wave 2 - Build Simplification and Release Governance (landed locally)

Gate:
- Wave 1 merged and docs-state clean

Deliverables:
- Electron archival
- Windows-first CI/release gate automation
- reproducible build/toolchain guidance
- build manifest generation for packaged Windows artifacts

### Wave 3 - Runtime and Data-Root Hard Cutover

Gate:
- build/release governance is established and the runtime contract is documented

Deliverables:
- `LYRA_DATA_ROOT` as mutable-data authority
- removal of repo-root mutable-data defaults
- migration and compatibility strategy for legacy layouts

### Wave 4 - Desktop Stack Modernization

Gate:
- runtime/data-root contract is stable enough to carry forward into host/runtime validation

Deliverables:
- Tauri and frontend stack modernization
- packaged-host revalidation on the upgraded stack

### Wave 5 - Metadata, Recommendation, and Oracle Expansion

Gate:
- host/build/runtime foundations remain green after earlier waves

Deliverables:
- provider-contract recommendation architecture
- richer metadata/community-source integration
- broader Oracle action depth

### Wave 6 - Product Surface Depth

Gate:
- recommendation and metadata evidence is available to surface in the UI

Deliverables:
- provenance-first UX
- clearer rationale and degraded-state reporting
- deeper Oracle/playlist/detail insight surfaces

### Wave 7 - Release-Gate Closure

Gate:
- all earlier waves are landed and documented

Deliverables:
- blank-machine installer validation
- full parity/audio soak
- final gap closure or restatement

## 7) Non-Negotiables

- No regressions to one-launch unified app behavior.
- No backend side quests without listening UX impact.
- No mandatory Docker dependency for daily playback.
- No new runtime dependency should default to Docker when it can be bundled or internalized.
- No forced oracle chatter while silent mode is selected.

## 8) North Star

Revelations per week:
recommended tracks that are both saved and replayed within 7 days.
