# Lyra: Engine to Entity - Unified Master Plan

Last updated: March 7, 2026

This file is the single forward-plan authority for Lyra.
It merges the original Engine-to-Entity vision with the Unified App Cutover execution track.

Execution sequencing, iteration order, owner splits, and handoff rules for the remaining waves live in `docs/PHASE_EXECUTION_COMPANION.md`.

## 1) Mission Lock

Lyra is a local-first media library and player powered by Lyra Core, the intelligence authority for discovery, playlist generation, listening memory, and explainable recommendations.

Core priorities:

- Library and player reliability are first-class. Basic playback, queueing, browsing, and playlist use must always work even when Lyra Core is unavailable, degraded, or still evolving.
- Lyra Core is the intelligence authority that makes the player smarter, more personal, more explainable, and more alive.
- Backend expansion only when it ships visible user value in the same or next wave.

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

1. Blank-machine installer proof against the finalized packaged/runtime contract is still pending.
2. Native audio production validation (`miniaudio`) on real devices/long sessions is still pending.
3. Oracle action breadth, metadata depth, and product explainability are still expandable after governance and build/runtime foundations are aligned.

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

### Wave 3 - Runtime and Data-Root Hard Cutover (landed locally)

Gate:
- build/release governance is established and the runtime contract is documented

Deliverables:
- `LYRA_DATA_ROOT` as mutable-data authority
- removal of repo-root mutable-data defaults
- migration and compatibility strategy for legacy layouts
 - explicit migrate-now/defer flow through CLI and runtime API

### Wave 4 - Desktop Stack Modernization (landed locally)

Gate:
- runtime/data-root contract is stable enough to carry forward into host/runtime validation

Deliverables:
- Tauri and frontend stack modernization
- packaged-host revalidation on the upgraded stack

### Wave 5 - Metadata, Recommendation, and Oracle Expansion (landed locally)

Gate:
- host/build/runtime foundations remain green after earlier waves

Deliverables:
- provider-contract recommendation architecture
- richer metadata/community-source integration
- broader Oracle action depth

### Wave 6 - Product Surface Depth (landed locally)

Gate:
- recommendation and metadata evidence is available to surface in the UI

Deliverables:
- provenance-first UX
- clearer rationale and degraded-state reporting
- deeper Oracle/playlist/detail insight surfaces

### Wave 7 - Release-Gate Closure (active)

Gate:
- all earlier waves are landed and documented

Deliverables:
- blank-machine installer validation
- full parity/audio soak
- final gap closure or restatement

Current status:
- packaged host smoke passes
- 60-second parity soak passes with rebuilt sidecar (Wave 5+6 modules included) and `-UseLegacyDataRoot` dev workaround
- full 4-hour soak deferred
- blank-machine proof remains blocked-external

Execution companion:
- `docs/PHASE_EXECUTION_COMPANION.md` extends the committed phase track beyond Wave 7 and defines iteration-level execution for Waves 3 through 11.

### Wave 16 - One Player (next after Wave 15)

Gate:
- Wave 15 is locally landed and docs-state is clean

Intent:
Consolidate Lyra from a capable multi-system project into one coherent local-first media library and player with Lyra Core as the intelligence authority. This is a docs/governance/product-shape and repository cleanup wave, not a broad implementation spree.

Deliverables:
- revised mission lock reflecting library + player + Lyra Core identity
- canonical product shape and surface responsibility definitions
- product law encoding library/player reliability as first-class
- surface labels: CANONICAL, COMPATIBILITY ONLY, LEGACY / PENDING ARCHIVE
- cleanup principle for obsolete architectural remnants
- repository cleanup of obsolete direction artifacts
- tightened agent instructions for canonical-surface-first behavior
- ordered follow-on waves (17 through 21) serving one coherent listening product

### waves 17 through 21 — forward plan

These waves are ordered to build on Wave 16's product-shape clarity. Each wave must improve the felt library/player/core experience, not broaden backend scope in isolation.

- **Wave 17 — Core Legibility:** make Lyra Core understandable on the surface — why this track, why now, what next, what changed from feedback
- **Wave 18 — Playlist Sovereignty:** make playlist creation, saved vibes, sequencing, editing, and replay the center of the product
- **Wave 19 — Discovery Graph:** bridge logic, adjacency, similarity growth, cross-genre movement, and confident discovery paths
- **Wave 20 — Listening Memory:** behavior-driven refinement, replay/save trust signals, session continuity, and taste drift recognition
- **Wave 21 — Release Confidence:** blank-machine installer proof, long-session audio validation, packaged runtime hardening, and release-gate closure

## 7) Non-Negotiables

- No regressions to one-launch unified app behavior.
- No backend side quests without listening UX impact.
- No mandatory Docker dependency for daily playback.
- No new runtime dependency should default to Docker when it can be bundled or internalized.
- No forced oracle chatter while silent mode is selected.

## 8) North Star

Revelations per week:
recommended tracks that are both saved and replayed within 7 days.

## 9) Canonical Product Shape

Lyra is one product with the following canonical surfaces and responsibilities:

| Surface | Primary responsibility | Archetype |
| --- | --- | --- |
| Home | Operate the current listening session; resume, control, branch playback | WorkspacePage |
| Library | Browse and act on owned catalog; filter, select, play, queue | ArchivePage |
| Search / Discover | Find material across library and semantic surfaces | ArchivePage |
| Playlist | Browse and play saved listening paths and vibes | ArchivePage / DetailPage |
| Player / Queue | Shape the active listening run; reorder, inspect, continue | WorkspacePage |
| Lyra Core / Oracle | Steer recommendation behavior; act on proposals; inspect why | RecommendationPage |

Canonical UI structure authority: `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md`.

Future waves must deliver improvements that a person using Lyra as their daily player would notice. Backend-only work that does not surface within the same or next wave is not permitted.

## 10) Product Law

1. Lyra must remain a dependable media library and player even when Lyra Core is unavailable, degraded, or still evolving.
2. Basic playback, queueing, browsing, and playlist usage are first-class product behavior.
3. Lyra Core is the intelligence authority that makes the player smarter, more personal, more explainable, and more alive.
4. Future work must improve library/player/core cohesion, not split them apart.
5. No future wave should weaken standalone player/library usefulness.
6. Once a canonical path is declared, obsolete alternatives should be removed, archived, or clearly quarantined so they do not continue to mislead development.

## 11) Surface Labels

Every runtime path, API surface, host, and UI entry should carry one of these labels:

- **CANONICAL:** the active, supported, and preferred path. All new work targets this surface.
- **COMPATIBILITY ONLY:** still functional but not the preferred path. Not actively improved. Exists to avoid breaking existing workflows during transition.
- **LEGACY / PENDING ARCHIVE:** no longer functional or actively maintained. Should be archived or removed when the canonical replacement is stable.

Cleanup principle: when a canonical path is declared and stable, compatibility-only paths should be frozen and legacy paths should be archived or removed in the next governance wave. The repo should present one obvious path, not a historically complete museum of dead alternatives.

## 12) Forward-Wave Cohesion

Every wave after Wave 16 must satisfy:

1. The wave improves the felt experience of using Lyra as a daily local-first media library and player.
2. Backend or intelligence work is justified by a visible surface improvement in the same or next wave.
3. The wave does not introduce new runtime paths, host alternatives, or UI frameworks that compete with the canonical product shape.
4. If a wave closes a gap, the matching gap registry entry, worklist, and project state are updated in the same pass.
