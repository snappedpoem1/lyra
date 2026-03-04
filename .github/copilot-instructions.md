# Lyra Oracle  Copilot Instructions

## Read These First  Every Session

Before writing any code, read:
- `C:\MusicOracle\.claude\memory\MEMORY.md`  live state, metrics, what works/broken, priorities
- `C:\MusicOracle\.claude\memory\SESSIONS.md`  recent change log

After each batch of changes, update both files. Numbers in this file go stale; MEMORY.md does not.


## Project
Local-first music intelligence system. Python 3.12, SQLite (`lyra_registry.db`), ChromaDB (`chroma_storage/`), Flask API, React 18 + TypeScript frontend. Windows, project root `C:\MusicOracle`, library on `A:\Music`.

## Stack
- **Backend**: Python 3.12, Flask, argparse CLI (`oracle/cli.py`), SQLite via `oracle/db/schema.py`
- **AI/Audio**: CLAP embeddings (`laion/larger_clap_music`), DirectML (AMD GPU), ChromaDB
- **Frontend**: React 18 + TypeScript + Vite + TanStack Router/Query + Zustand + Framer Motion
- **Acquisition**: 5-tier waterfall — Qobuz → Streamrip → Slskd → Real-Debrid → SpotDL

## Coding rules
- `pathlib.Path` always — never `os.path`
- `logging.getLogger(__name__)` — never `print()`
- Parameterized SQL only — `?` placeholders, never f-strings in queries
- Type hints on all signatures, Google docstrings
- All paths from `oracle/config.py` — never hardcoded
- snake_case files/functions, PascalCase classes, UPPER_SNAKE constants

## Key modules
- `oracle/db/schema.py` — `get_connection()`, all migrations
- `oracle/config.py` — all env-backed config (LIBRARY_BASE, CHROMA_PATH, etc.)
- `oracle/acquirers/waterfall.py` — acquisition cascade
- `oracle/acquirers/guard.py` — pre/post acquisition validation (never weaken)
- `oracle/scorer.py` — 10-dimensional CLAP scoring (energy/valence/tension/density/warmth/movement/space/rawness/complexity/nostalgia)
- `oracle/api/__init__.py` — Flask app factory
- `oracle/api/blueprints/` — all API routes

## The 10 dimensions
energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
(not "darkness" or "transcendence" — those don't exist)

