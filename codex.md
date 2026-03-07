# Lyra Oracle - Codex Project Instructions

This file is read by Codex CLI as project-level context.
Root `AGENTS.md` is the primary policy source.

## Project Identity

Lyra is a local-first media library and player powered by Lyra Core, the intelligence authority. It is not a generic dashboard.

- Python 3.12 + Flask API + SQLite (`lyra_registry.db`) + ChromaDB (`chroma_storage/`)
- CLAP embeddings via DirectML on Windows
- Tauri host + React 18 + TypeScript + Vite renderer
- 10-dimensional emotional scoring:
  `energy`, `valence`, `tension`, `density`, `warmth`, `movement`, `space`, `rawness`, `complexity`, `nostalgia`
- 5-tier acquisition waterfall:
  Qobuz -> Streamrip -> Slskd -> Real-Debrid -> SpotDL

## Environment

- OS: Windows 11 (PowerShell)
- Python: `.venv\Scripts\python.exe`
- Renderer: `desktop\renderer-app\`
- Runtime paths from `oracle/config.py` only
- Never delete or reset `lyra_registry.db` or `chroma_storage/`

## Coding Rules

- `pathlib.Path` always
- `logging.getLogger(__name__)` always
- Parameterized SQL only (`?`)
- Type hints on all signatures
- No invented emotional dimensions

## Validation Commands

```powershell
python -m pytest -q
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Ground Truth Read Order

1. `AGENTS.md`
2. `docs/ROADMAP_ENGINE_TO_ENTITY.md`
3. `docs/PROJECT_STATE.md`
4. `docs/MISSING_FEATURES_REGISTRY.md`
5. `docs/WORKLIST.md`
6. `docs/SESSION_INDEX.md`

## Session Protocol

Before behavior-changing work:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

Use session-prefixed commits:

`[S-YYYYMMDD-NN] <type>: <description>`

## Done Criteria

- Tests/build pass
- docs state files updated
- session log + session index updated
- docs QA script passes
