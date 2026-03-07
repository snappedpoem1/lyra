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

## Current State

- Waves 10 through 14 are complete locally.
- Release-gate follow-up remains separate from the implementation sequence:
  - blank-machine installer proof is blocked-external
  - 4-hour parity/audio soak remains deferred
- `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` remains the structural authority for broader frontend refactors.

## Next Up

1. Continue `oracle mbid resolve` passes until recording MBID coverage is high enough for broad credit enrichment, then run `oracle credits enrich --limit 500`.
2. Open Wave 15 with one bounded lane:
   - structure analysis coverage hardening (`G-032`)
   - similarity graph growth (`G-030`)
   - acquisition waterfall improvements
3. Resume blank-machine installer proof once a clean Windows machine or VM is available.
4. Run full 4-hour parity soak when the release-gate lane is reopened.
5. Use `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` before any broader cross-route frontend refactor.
