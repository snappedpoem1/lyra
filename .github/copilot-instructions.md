# Lyra Oracle - Copilot Instructions

## Project
Local-first music intelligence system. Python 3.12, SQLite (`lyra_registry.db`), ChromaDB (`chroma_storage/`), Flask API, React 18 + TypeScript frontend. Windows-first, repo-root runtime, local library workflow.

## Stack
- **Backend**: Python 3.12, Flask, argparse CLI (`oracle/cli.py`), SQLite via `oracle/db/schema.py`
- **AI/Audio**: CLAP embeddings (`laion/larger_clap_music`), DirectML (AMD GPU), ChromaDB
- **Frontend**: React 18 + TypeScript + Vite + TanStack Router/Query + Zustand + Framer Motion
- **Acquisition**: 5-tier waterfall - Qobuz -> Streamrip -> Slskd -> Real-Debrid -> SpotDL

## Coding rules
- `pathlib.Path` always - never `os.path`
- `logging.getLogger(__name__)` - never `print()`
- Parameterized SQL only - `?` placeholders, never f-strings in queries
- Type hints on all signatures, Google docstrings
- All paths from `oracle/config.py` - never hardcoded
- snake_case files/functions, PascalCase classes, UPPER_SNAKE constants

## Key modules
- `oracle/db/schema.py` - `get_connection()`, all migrations
- `oracle/config.py` - env-backed config
- `oracle/acquirers/waterfall.py` - acquisition cascade
- `oracle/acquirers/guard.py` - pre/post acquisition validation
- `oracle/scorer.py` - 10-dimensional CLAP scoring
- `oracle/api/__init__.py` - Flask app factory
- `oracle/api/blueprints/` - API routes

## The 10 dimensions
energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia

Do not refer to non-existent dimensions like `darkness` or `transcendence`.

## Validation commands
```powershell
python -m pytest -q                                               # backend tests (must stay green)
cd desktop\renderer-app && npm run test && npm run build          # renderer tests + build
powershell -ExecutionPolicy Bypass -File scripts/smoke_desktop.ps1 -AllowLlmFailure  # e2e smoke
```

## Session tracking — mandatory on every behavior-changing PR

Every PR or commit that changes observable behavior must also update:

1. `docs/SESSION_INDEX.md` — add or update the row for this session
2. `docs/sessions/YYYY-MM-DD-<slug>.md` — create or update the session log file
3. `docs/PROJECT_STATE.md` — if metrics, module status, or architecture changed
4. `docs/WORKLIST.md` — if done/next items changed

To start a new session:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-slug" -Goal "My goal"
```

Use the printed Session ID as the commit message prefix: `[S-YYYYMMDD-NN] type: description`

See `AGENTS.md` for the full session protocol and ground-truth file list.
