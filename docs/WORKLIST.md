# Worklist

Last updated: March 7, 2026 (post-Wave 14 sync)

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

## Current State

- Waves 10 through 14 are complete locally.
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
