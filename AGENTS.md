# AGENTS.md — Lyra Oracle Agent Instructions

> Read this file first. It is the authoritative entry point for all agent tooling
> (GitHub Copilot coding agent, Codex, and any repo-aware assistant).

---

## What Lyra Is

Lyra Oracle is a **local-first music intelligence system** built for personal library ownership.

- Python 3.12 backend + Flask API
- SQLite primary store (`lyra_registry.db`)
- ChromaDB vector store (`chroma_storage/`)
- CLAP embeddings (`laion/larger_clap_music`) via DirectML (AMD GPU)
- React 18 + TypeScript + Vite desktop renderer (Electron direction)
- 10-dimensional emotional scoring: `energy`, `valence`, `tension`, `density`, `warmth`, `movement`, `space`, `rawness`, `complexity`, `nostalgia`
- 5-tier acquisition waterfall: Qobuz → Streamrip → Slskd → Real-Debrid → SpotDL

It is **not** a generic dashboard or streaming app. It runs on Windows against a real local library
with real metadata ambiguity, and every design decision should respect that context.

---

## Ground Truth Files — Read Before Changing Anything

| File | Purpose |
|---|---|
| `docs/PROJECT_STATE.md` | Audited snapshot of repo + runtime (treat as facts) |
| `docs/MISSING_FEATURES_REGISTRY.md` | Real gaps, partials, and integration issues |
| `docs/WORKLIST.md` | Short done/todo list for the active cycle |
| `docs/SESSION_INDEX.md` | Table of all work sessions |
| `.claude/CLAUDE.md` | Claude Code working memory (legacy, may diverge from root `CLAUDE.md`) |

**Rule:** Do not propose changes that contradict `docs/PROJECT_STATE.md` without updating
`docs/PROJECT_STATE.md` in the same PR/commit.

---

## Coding Rules

- `pathlib.Path` always — never `os.path`
- `logging.getLogger(__name__)` — never `print()`
- Parameterized SQL only — `?` placeholders, never f-strings in queries
- Type hints on all signatures; Google-style docstrings
- All paths sourced from `oracle/config.py` — never hardcoded
- `snake_case` for files/functions, `PascalCase` for classes, `UPPER_SNAKE` for constants
- Do not invent dimensions — the 10 above are the complete set

---

## Key Modules

| Module | Role |
|---|---|
| `oracle/config.py` | Env-backed config — single source of all runtime paths |
| `oracle/db/schema.py` | `get_connection()` and all migrations |
| `oracle/scorer.py` | 10-dimensional CLAP scoring |
| `oracle/acquirers/waterfall.py` | Acquisition cascade |
| `oracle/acquirers/guard.py` | Pre/post acquisition validation |
| `oracle/api/__init__.py` | Flask app factory |
| `oracle/api/blueprints/` | API route handlers |

---

## Build, Test, and Validation Commands

```powershell
# Backend tests (must stay green)
python -m pytest -q

# Renderer tests + production build
cd desktop\renderer-app
npm run test
npm run build

# End-to-end smoke (recommended before any PR)
powershell -ExecutionPolicy Bypass -File scripts/smoke_desktop.ps1 -AllowLlmFailure

# System health
python -m oracle doctor
python -m oracle status
```

All commands are run from the repo root on Windows with `.venv` active.

---

## Session System Rules

Every work session that changes behavior must:

1. Create a session log: `docs/sessions/YYYY-MM-DD-<slug>.md` (use `scripts/new_session.ps1`)
2. Add one row to `docs/SESSION_INDEX.md`
3. Update `docs/PROJECT_STATE.md` if facts changed (metrics, status, architecture)
4. Update `docs/WORKLIST.md` if done/next items changed
5. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap was closed or newly found

**Session ID format:** `S-YYYYMMDD-NN` where `NN` is a zero-padded counter for that day.

**Commit message prefix:** `[S-YYYYMMDD-NN] <type>: <description>`

To start a new session:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

---

## What "Done" Means

A task is **done** when:

- Code changes pass `python -m pytest -q` (64+ tests green)
- If renderer was touched: `npm run test` and `npm run build` pass
- `docs/PROJECT_STATE.md` reflects the new truth
- `docs/SESSION_INDEX.md` has a row for this session
- `docs/sessions/<session-file>.md` exists with a result summary
- No broken relative Markdown links in tracked `.md` files

A task is **not done** if code shipped but documentation was skipped.
