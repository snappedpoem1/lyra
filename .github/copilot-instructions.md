# Lyra Oracle - Copilot Instructions

## Project

Local-first media library and player powered by Lyra Core, for a personally owned library.
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
- Legacy Python runtime paths (reference only) come from `archive/legacy-runtime/oracle/config.py`
- Do not invent emotional dimensions

## Canonical Playback Contract

- Legacy backend player reference lives in `archive/legacy-runtime/oracle/player/*`
- UI transport actions call `/api/player/*`
- `/ws/player` is an SSE stream endpoint
- `/api/playback/record` is compatibility-only

## Repo-Wide Operating Rules

- Run `scripts/new_session.ps1` for behavior-changing work
- Update session artifacts when behavior or repo truth changes
- If a task affects roadmap/state/worklist/registry/agent coordination, update docs first before implementation
- Legacy Python runtime paths (reference only) come from `archive/legacy-runtime/oracle/config.py`
- Tauri is the only supported desktop host path
- If working in parallel with another agent on the same wave, read `docs/agent_briefs/tandem-wave-protocol.md` and stay inside the assigned non-overlapping file set

Lane-specific guidance lives in `.github/instructions/*.instructions.md` and relevant `docs/agent_briefs/*.md` files.
