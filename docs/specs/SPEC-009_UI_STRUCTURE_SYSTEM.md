# SPEC-009: Lyra UI Structure System

## 1. Objective

Define the structural layer above Figma and the primitive UI library so future Lyra UI work is driven by route purpose, shell responsibility, and evidence rules instead of ad hoc page composition.

This spec is docs-only. It does not require immediate renderer refactors and is safe to land while other phase work is active.

## 2. Inputs and Defaults

Current repo truths this spec builds on:

- the renderer uses one persistent application shell in `AppShell`
- routes are defined in `desktop/renderer-app/src/app/router.tsx`
- the primitive UI layer is intentionally small (`LyraPanel`, `LyraButton`, `LyraPill`, `LyraTabs`, icons, context menu)
- bespoke shell styling already exists across multiple routes, but the route composition rules are not yet written down
- provenance and degraded-state rendering requirements already exist in `SPEC-005`

Default decisions:

- keep Figma
- keep the current primitive UI library small
- treat structure as more important than component count
- do docs/spec/audit work before any broad renderer refactor

## 3. Route Inventory and Primary Archetypes

Every route must have exactly one primary archetype even if it supports secondary behaviors.

| Route | Primary archetype | User job | Primary action | Supporting context |
| --- | --- | --- | --- | --- |
| `/` (Home / Now Playing) | `WorkspacePage` | operate the current listening session | resume, control, branch playback | queue state, recommendation context, live playback telemetry |
| `/queue` | `WorkspacePage` | shape the active listening run | reorder, inspect, continue playback | source/origin, current track, next-up context |
| `/library` | `ArchivePage` | browse and act on owned catalog slices | filter, select, play, queue | artist/album slice context, current browse state |
| `/search` | `ArchivePage` | find material across library and semantic surfaces | search, inspect, act on results | search mode, result provenance, current route context |
| `/vibes` | `ArchivePage` | browse reusable vibe entry points | open and start a vibe path | featured vibe framing, archive list context |
| `/playlists` | `ArchivePage` | browse saved listening paths | open or start a playlist | playlist count, saved context, route-level summary |
| `/playlists/$playlistId` | `DetailPage` | inspect and run one saved listening thread | play, queue, inspect the playlist thread | playlist metadata, rationale, route-level signal strip |
| `/artist/$name` | `DetailPage` | inspect one artist as an entity | explore tracks, lineage, and related context | scores, similar context, discographic or graph depth |
| `/oracle` | `RecommendationPage` | steer recommendation behavior and act on proposals | change mode, play, queue, inspect why | seed track, provider evidence, degraded state, constellation context |
| `/settings` | `SystemPage` | inspect and control system/runtime settings | change configuration, run diagnostics | backend health, doctor output, connection/runtime status |

Notes:

- `RecommendationPage` is intentionally distinct from `WorkspacePage`.
- Oracle is not just a control screen. Its main job is recommendation steering plus explainable decision support.
- secondary panels inside a route must not change the route's primary archetype.

## 4. Shell Responsibility Map

Persistent shell regions must keep a single responsibility and must not absorb route-specific layout problems.

| Shell region | Current surface | Responsibility | Must not become |
| --- | --- | --- | --- |
| Left rail | `LeftRail` | global navigation, connectivity snapshot, lightweight now-playing jump | a route-local filter stack or diagnostics canvas |
| Top bar | `TopAtmosphereBar` | app/session status, boot/connectivity state, window controls | a per-route metrics board or recommendation surface |
| Right rail | `RightRail` | contextual detail, dossier, queue detail, provenance-adjacent supporting context | the primary content area for any route |
| Bottom dock | `BottomTransportDock` | playback transport, timeline, fact drop, immediate playback telemetry | library browsing, recommendation browsing, or diagnostics control center |
| Overlays and drawers | command palette, semantic search, dossier drawer, companion, developer HUD | transient or interruptible tasks that must not claim permanent route space | substitutes for missing route structure |

Structural rules:

1. Persistent shell regions hold global or cross-route context.
2. Route bodies hold the route's main job.
3. Overlays and drawers hold temporary tasks, not permanent information architecture.
4. Route-level metrics belong in the route body, not the top bar.
5. Recommendation explanation belongs in route or rail surfaces that already own recommendation context; it must not be hidden only in drawers.

## 5. Action Hierarchy

All UI actions must be classified before new surface work starts.

### 5.1 Primary actions

The main task the route exists to support.

Examples:

- play or queue from Library
- change recommendation mode and act on Oracle cards
- reorder or continue Queue
- run diagnostics or change settings in Settings

### 5.2 Contextual actions

Actions attached to the currently focused entity or row.

Examples:

- inspect track dossier
- open artist detail from current playback
- inspect provenance details for one recommendation

### 5.3 Ambient actions

Global actions available regardless of route.

Examples:

- command palette
- semantic search overlay
- play/pause, next/previous, seek, mute

Rule:

- primary actions must be visible in the route body
- contextual actions may live in the right rail or details views
- ambient actions belong to shell regions or overlays

## 6. Page Archetype Contracts

### 6.1 `WorkspacePage`

Use when the route is an active control deck.

Required zones:

- compact or medium hero/header
- operational summary strip
- main interactive board
- supporting context region for secondary insight
- explicit empty state when there is no active session material

Examples:

- Home
- Queue

### 6.2 `ArchivePage`

Use when the route is primarily about browse, filter, or selection over a collection.

Required zones:

- archive hero/header
- current slice or browse-state summary
- filters and sort controls near the top of the main flow
- collection/list/grid area
- explicit empty, no-result, and degraded data states

Examples:

- Library
- Search
- Vibes
- Playlists

### 6.3 `DetailPage`

Use when one entity anchors the page.

Required zones:

- entity or thread hero
- summary metrics strip
- canonical detail content region
- supporting rationale, lineage, or provenance region
- explicit missing-data and weak-context states

Examples:

- Playlist detail
- Artist

### 6.4 `RecommendationPage`

Use when recommendation steering and explainability are the route's primary job.

Required zones:

- observatory or steering hero
- mode/control zone
- recommendation list or card deck
- visible provenance and confidence summary at scan level
- degraded-state banner before the user acts
- progressive technical trace/details region

Examples:

- Oracle

### 6.5 `SystemPage`

Use when the route exists to control or inspect runtime and diagnostics state.

Required zones:

- system summary hero
- health/status summary strip
- diagnostics and controls region
- warning/failure callouts before deeper detail
- explicit unavailable/degraded service states

Examples:

- Settings

## 7. Semantic UI Blocks

These blocks sit above primitives and below full page templates. They should be introduced only when reuse is real.

| Block | Purpose | Expected reuse | Ownership |
| --- | --- | --- | --- |
| Hero section | route identity, short framing copy, top-level status | all archetypes | route-structure layer |
| Metric strip | compact counts, state bands, or health summary | workspace, archive, detail, system, recommendation pages | route-structure layer |
| Action cluster | primary route actions grouped with clear hierarchy | all archetypes | route-structure layer |
| Provenance row | provider chips, confidence, degraded status | recommendation and detail surfaces | evidence/explainability layer |
| Degraded-state banner | visible warning before action | recommendation and system surfaces; archive/detail when source quality is weak | evidence/explainability layer |
| System summary panel | compact status-plus-action frame | settings, diagnostics, runtime panels | diagnostics layer |
| Recommendation card shell | compact recommendation surface with expandable why-this section | Oracle and future recommendation-bearing surfaces | evidence/explainability layer |

Rule:

- primitives remain generic
- semantic blocks encode repeated meaning, not one-off styling
- page templates compose semantic blocks

## 8. Do Not Abstract Yet

The following patterns are still route-specific and must not be prematurely turned into shared abstractions:

- constellation visualization
- vibe featured-card storytelling treatment
- playlist thread-specific hero copy patterns
- artist lineage and profile framing
- bottom dock waveform presentation
- companion-specific conversational panels

These can be revisited only after at least two stable routes need the same structural behavior.

## 9. Provenance and Degraded-State Placement

`SPEC-005` remains the authority for provenance payload rendering. This spec decides where those elements belong structurally.

Placement rules:

1. Recommendation surfaces must show provider/confidence/degraded signals at scan level.
2. Technical trace stays collapsed by default.
3. Right-rail details may deepen provenance, but must not be the first place users see degraded-state warnings.
4. Playlist detail, Oracle, now-playing insight surfaces, and right-rail recommendation-supporting panels must map directly to backend evidence.
5. UI must not infer unsupported rationale text that is not represented in payload or mapped copy rules.

## 10. Implementation Waves for Future Renderer Work

This is not a new roadmap wave. It is the frontend execution sequence to apply when the active product wave opens safe UI work.

### 10.1 Docs-only wave

Deliver:

- this spec
- route audit
- shell responsibility map
- archetype contracts
- semantic block catalog

### 10.2 Low-risk renderer wave

Deliver:

- non-invasive page wrapper components for the archetypes
- semantic blocks that already have real repetition

Guardrails:

- no shell-wide rewrite
- no active-wave collision with other owners

### 10.3 Surface adoption wave

Deliver:

- migrate one route family at a time
- start with routes already closest to the archetypes

Suggested order:

1. Archive pages
2. Detail pages
3. System pages
4. Recommendation pages

### 10.4 Explainability depth wave

Deliver:

- apply `SPEC-005` consistently across Oracle, playlist detail, right rail, and now-playing insight surfaces

## 11. Validation

Planning validation:

1. Every route has exactly one primary archetype.
2. Every persistent shell region has a single responsibility.
3. Recommendation surfaces have a defined provenance and degraded-state placement.
4. Docs-only planning does not require renderer file mutation.

Later implementation validation:

```powershell
cd desktop\renderer-app
npm run test:ci
npm run build
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## 12. Acceptance Criteria

This spec is satisfied when future Lyra UI work can answer all of the following before implementation starts:

- what archetype is this route?
- what is the route's primary job?
- what stays in the shell versus the route body?
- where do provenance and degraded states appear?
- what should be a semantic block versus a one-off route pattern?

If those questions cannot be answered from docs alone, UI work is still under-specified.
