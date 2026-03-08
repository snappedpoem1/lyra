# CLAUDE.md - Persistent Memory for Lyra Oracle

Keep this file synchronized with current repo truth.

## Read Order

1. `AGENTS.md`
2. `docs/ROADMAP_ENGINE_TO_ENTITY.md`
3. `docs/LEGACY_MIGRATION_REGISTRY.md`
4. `docs/PROJECT_STATE.md`
5. `docs/MISSING_FEATURES_REGISTRY.md`
6. `docs/WORKLIST.md`
7. `docs/SESSION_INDEX.md`

## Project Identity

Lyra is a local-first media library and player powered by Lyra Core, the intelligence authority.
Current desktop host direction is Tauri-only.
Canonical playback authority is backend player state in `oracle/player/*`.

## Current Truth Snapshot (March 7, 2026)

- Tracks indexed: 2,454
- Scored tracks: 2,454
- Embeddings: 2,454
- Spotify history rows: 127,312
- Playback events: 30,680
- Backend tests: 300 passing
- Frontend tests: 41 passing

For full audit detail, use `docs/PROJECT_STATE.md`.

## Working Rules

- Trust code + local runtime data over stale docs.
- Do not claim completion without code/runtime verification.
- Keep docs and session artifacts updated with behavior changes.
- Treat foobar/BeefWeb as historical compatibility context, not current delivery gate.

## Session Close Requirements

When behavior changes:

1. Update `docs/PROJECT_STATE.md` (if facts changed)
2. Update `docs/WORKLIST.md`
3. Update `docs/MISSING_FEATURES_REGISTRY.md` (if gap status changed)
4. Update `docs/SESSION_INDEX.md`
5. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
6. Run tests/build
7. Run docs QA:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```
