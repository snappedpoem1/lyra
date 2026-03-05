# Lyra Oracle — Codex Project Instructions

> This file is read by OpenAI Codex CLI as project-level context.
> Root `AGENTS.md` carries the full coding rules and session protocol.
> This file provides Codex-specific startup context and safety guards.

---

## Project Identity

**Lyra Oracle** is a local-first music intelligence system, not a generic dashboard.

- Python 3.12 + Flask API + SQLite (`lyra_registry.db`) + ChromaDB (`chroma_storage/`)
- CLAP embeddings via DirectML (AMD GPU) on Windows
- React 18 + TypeScript + Vite desktop renderer
- 10-dimensional emotional scoring: `energy`, `valence`, `tension`, `density`, `warmth`, `movement`, `space`, `rawness`, `complexity`, `nostalgia`
- 5-tier acquisition waterfall: Qobuz → Streamrip → Slskd → Real-Debrid → SpotDL

Do **not** invent dimensions. Do **not** assume a web app context.

---

## Environment

- OS: Windows 11 (PowerShell primary shell)
- Python: `.venv\Scripts\python.exe` from repo root
- Node: `desktop\renderer-app\` for renderer work
- All paths via `oracle/config.py` — never hardcoded
- Runtime DB and vector store live at repo root; do **not** delete or reset them

---

## Shell Setup (Codex sandbox)

```shell
# Activate Python env before any python commands
.venv\Scripts\Activate.ps1

# Or prefix directly:
.venv\Scripts\python.exe -m pytest -q
```

---

## Coding Rules

- `pathlib.Path` always — never `os.path`
- `logging.getLogger(__name__)` — never `print()`
- Parameterized SQL only — `?` placeholders, never f-strings in queries
- Type hints on all signatures; Google-style docstrings
- `snake_case` files/functions, `PascalCase` classes, `UPPER_SNAKE` constants
- All paths sourced from `oracle/config.py`

---

## Validation Commands

```powershell
# Must stay green before any commit
python -m pytest -q

# Renderer (when frontend is touched)
cd desktop\renderer-app
npm run test
npm run build
```

---

## Ground Truth Files (Read Before Changing Anything)

| File | Purpose |
|---|---|
| `docs/PROJECT_STATE.md` | Audited facts — treat as ground truth |
| `docs/MISSING_FEATURES_REGISTRY.md` | Real gaps and partials |
| `docs/WORKLIST.md` | Active cycle tasks |
| `docs/SESSION_INDEX.md` | All session history |
| `AGENTS.md` | Full coding rules + session protocol |

Do not propose changes that contradict `docs/PROJECT_STATE.md` without updating it in the same commit.

---

## Session Protocol

Every commit that changes observable behavior must:

1. Create `docs/sessions/YYYY-MM-DD-<slug>.md` (run `scripts/new_session.ps1`)
2. Add a row to `docs/SESSION_INDEX.md`
3. Update `docs/PROJECT_STATE.md` if facts changed

Use the session ID as the commit prefix: `[S-YYYYMMDD-NN] type: description`

```powershell
# Start every session:
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

---

## What "Done" Means

- `python -m pytest -q` passes (64+ tests)
- If renderer touched: `npm run test` + `npm run build` pass
- `docs/PROJECT_STATE.md` reflects current reality
- Session log exists in `docs/sessions/` with a result summary
- `docs/SESSION_INDEX.md` has a row for this session

A task is **not done** if code shipped but these artifacts were skipped.
