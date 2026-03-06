# Lyra Oracle - Copilot Instructions

## Project

Local-first music intelligence system for a personally owned library.
Primary target is Windows 11.

Stack:

- Backend: Python 3.12, Flask, SQLite (`lyra_registry.db`), Chroma (`chroma_storage/`)
- Audio/ML: CLAP embeddings, DirectML-friendly runtime, `miniaudio` backend playback
- Desktop: Tauri host + React 18 + TypeScript + Vite renderer
- Acquisition: Qobuz -> Streamrip -> Slskd -> Real-Debrid -> SpotDL

## Core Rules

- Always use `pathlib.Path`, never `os.path`
- Always use module logger, never `print()`
- Always use parameterized SQL (`?`)
- Type hints on all function signatures
- Runtime paths come from `oracle/config.py`
- Do not invent emotional dimensions

## Canonical Playback Contract

- Backend player (`oracle/player/*`) is source of truth
- UI transport actions call `/api/player/*`
- `/ws/player` is an SSE stream endpoint
- `/api/playback/record` is compatibility-only

## Validation Commands

```powershell
python -m pytest -q
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\smoke_desktop.ps1 -AllowLlmFailure
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Tracking (Required)

For behavior-changing work:

1. Run `scripts/new_session.ps1`
2. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
3. Update `docs/SESSION_INDEX.md`
4. Update `docs/PROJECT_STATE.md` if facts changed
5. Update `docs/WORKLIST.md` if done/next changed
6. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap changed
