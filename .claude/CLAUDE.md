# .claude/CLAUDE.md - Legacy Mirror

Root `CLAUDE.md` is the authoritative Claude memory file.
This mirror exists for compatibility with older local workflows.

## Read Order

1. `../CLAUDE.md`
2. `../AGENTS.md`
3. `../docs/ROADMAP_ENGINE_TO_ENTITY.md`
4. `../docs/PROJECT_STATE.md`
5. `../docs/MISSING_FEATURES_REGISTRY.md`
6. `../docs/WORKLIST.md`

## Current Direction Lock

- Tauri-only desktop host path
- Backend player domain (`oracle/player/*`) is canonical playback source
- `/ws/player` is SSE event stream contract
- Docker is optional for acquisition, not required for daily local playback

## Update Policy

If this file and root `CLAUDE.md` diverge, root `CLAUDE.md` wins.
