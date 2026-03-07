# Worklist

Last updated: March 7, 2026 (post-Wave 17 sync)

This file tracks active execution work only.

## Completed Recently

- Wave 10 landed:
  - MBID identity spine is live through `SPEC-010`, `oracle/enrichers/mb_identity.py`, and `oracle mbid resolve|stats`
  - `CreditMapper.map_batch()` now uses `recording_mbid` correctly
  - backend suite reached `201 passed`
- Wave 11 landed:
  - companion pulse is live through `SPEC-011`, `oracle/companion/pulse.py`, and `/ws/companion`
  - renderer companion is now event-driven through `useCompanionStream.ts` and `companionLines.ts`
  - backend suite reached `215 passed`; renderer tests/build stayed green
- Wave 12 landed:
  - oracle action breadth now includes volume, queue clearing, repeat/shuffle controls, and artist/album/similar-play actions
  - backend suite reached `226 passed`
- Wave 13 landed:
  - named playlist intelligence is live through SQLite schema, `playlists.py`, oracle action routes, and gateway helpers
  - backend suite reached `241 passed`
- Wave 14 landed:
  - saved playlist UI is live in `PlaylistsRoute` through `SavedPlaylistsSection` and `CreatePlaylistModal`
  - saved-playlist mapper support and `PlaylistKind = "saved"` are now in place
  - renderer `vitest` reached `34 passed`; build stayed green
- Docs navigation cleanup landed:
  - folder guides now exist in `docs/`, `docs/sessions/`, `docs/specs/`, `docs/research/`, and `docs/agent_briefs/`
- Wave 15 (Copilot lane) landed:
  - `oracle biographer stats` `UnboundLocalError` fixed in `oracle/cli.py`
  - `GET /api/stats/revelations` endpoint added to `oracle/api/blueprints/core.py`
  - `oracle/duplicates.py` created with exact-hash + metadata-fuzzy + path duplicate detection
  - `GET /api/duplicates/summary` and `GET /api/duplicates` endpoints added to `intelligence.py`
  - vibe→`saved_playlists` bridge wired in `oracle/vibes.py` `save_vibe()` using deterministic UUID5
  - 30 new tests (test_duplicates.py, test_revelations.py, test_vibe_bridge.py); backend suite now `271 passed`
- Wave 16 (One Player governance) landed:
  - canonical/compatibility/legacy surface labels defined
  - `docs/CANONICAL_PATHS.md` added as short canonical path registry
  - follow-on Waves 17-21 defined and ordered
- Wave 17 (Core Legibility) landed:
  - `oracle/explainability.py` created: reusable explanation engine with `generate_explanation`, `generate_explanation_chips`, `generate_why_now`, `generate_what_next`, `generate_feedback_effect_description`, `get_recent_feedback_effects`, `summarize_feedback_direction`
  - broker wiring: `recommendation_broker.py` now enriches candidates with `explanation_chips` and `what_next` via explainability module
  - `GET /api/recommendations/feedback-effects` endpoint added returning recent feedback effects with direction summary
  - frontend: `ExplanationChipData`, `FeedbackEffect`, `FeedbackDirection`, `WhatNextHint` types in `domain.ts`
  - frontend: `features/explanations/` created with `ExplanationChips`, `ExplanationPanel`, `FeedbackActions`, `FeedbackEffectBanner`
  - `OracleRecommendationDeck` refactored to use explanation components with inline feedback actions
  - `oracleRoute`, `homeRoute`, `queueRoute`, and `BottomTransportDock` updated with legibility surfaces
  - `queries.ts` and `schemas.ts` updated for `explanation_chips`, `what_next`, and feedback-effects mapping
  - CSS: explanation chip, explanation panel, feedback action, and feedback effect banner styles added to `global.css`
  - 29 new backend tests (`test_explainability.py`); backend suite now `300 passed`; renderer `41 passed`

## Current State

- Waves 10 through 17 are complete locally.
- Release-gate follow-up remains separate from the implementation sequence:
  - blank-machine installer proof is blocked-external
  - 4-hour parity/audio soak remains deferred
- `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` remains the structural authority for broader frontend refactors.

## Next Up

1. Continue `oracle mbid resolve` passes until recording MBID coverage is high enough for broad credit enrichment, then run `oracle credits enrich --limit 500`.
2. Wave 15 Codex lane: native OS notifications (P1), global shortcuts (P2), native state persistence (P3) per `docs/agent_briefs/wave15-codex-brief.md`.
3. Structure analysis coverage hardening (`G-032`) and similarity graph growth (`G-030`) as background enrichment passes.
4. Resume blank-machine installer proof once a clean Windows machine or VM is available.
5. Run full 4-hour parity soak when the release-gate lane is reopened.
6. Use `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` before any broader cross-route frontend refactor.

## Wave 16: One Player (next docs/governance/product-shape and repo cleanup wave)

Gate:
- Wave 15 is locally landed and docs-state is clean

Intent:
Consolidate Lyra from a capable multi-system project into one coherent local-first media library and player with Lyra Core as the intelligence authority. Docs/governance/product-shape and repo cleanup only — not a broad implementation spree.

Deliverables:
1. Revised mission lock: library + player + Lyra Core identity
2. Canonical product shape and surface responsibility definitions
3. Product law encoding library/player reliability as first-class
4. Surface labels: CANONICAL, COMPATIBILITY ONLY, LEGACY / PENDING ARCHIVE
5. Cleanup principle for obsolete architectural remnants
6. Repository cleanup of obsolete direction artifacts (Electron stubs, dead renderer paths, stale references)
7. Tightened agent instructions for canonical-surface-first behavior
8. Added `docs/CANONICAL_PATHS.md` as short canonical path registry
9. Ordered follow-on waves (17 through 21) serving one coherent listening product

## Follow-On Waves (ordered after Wave 16)

These waves are ordered to build on Wave 16's product-shape clarity. Each must improve the felt experience of using Lyra as a daily player.

- **Wave 17 — Core Legibility:** DONE — explainability engine, explanation chips, feedback effect tracking, why/why-now/what-next across all main surfaces
- **Wave 18 — Playlist Sovereignty:** make playlist creation, saved vibes, sequencing, editing, and replay the center of the product
- **Wave 19 — Discovery Graph:** bridge logic, adjacency, similarity growth, cross-genre movement, and confident discovery paths
- **Wave 20 — Listening Memory:** behavior-driven refinement, replay/save trust signals, session continuity, and taste drift recognition
- **Wave 21 — Release Confidence:** blank-machine installer proof, long-session audio validation, packaged runtime hardening, and release-gate closure
