# AGENTS.md - Lyra Oracle Agent Instructions

Read this file first. It is the authoritative entry point for repo-aware agents.

## What Lyra Is

Lyra is a local-first media library and player powered by Lyra Core, the intelligence authority for discovery, playlist generation, listening memory, and explainable recommendations.

- Python 3.12 backend + Flask API
- SQLite primary store (`lyra_registry.db`)
- ChromaDB vector store (`chroma_storage/`)
- CLAP embeddings (`laion/larger_clap_music`) via DirectML on Windows
- Tauri host + React 18 + TypeScript + Vite renderer
- 10-dimensional emotional scoring:
  `energy`, `valence`, `tension`, `density`, `warmth`, `movement`, `space`, `rawness`, `complexity`, `nostalgia`
- 5-tier acquisition waterfall:
  Qobuz -> Streamrip -> Slskd -> Real-Debrid -> SpotDL

Lyra must remain a dependable media library and player even when Lyra Core is unavailable, degraded, or still evolving. It is not a generic dashboard or streaming app.

## Ground Truth Files

Read these before proposing behavior changes:

- `docs/ROADMAP_ENGINE_TO_ENTITY.md` (single forward plan authority)
- `docs/PROJECT_STATE.md` (audited runtime snapshot)
- `docs/MISSING_FEATURES_REGISTRY.md` (active gaps)
- `docs/WORKLIST.md` (active execution list)
- `docs/SESSION_INDEX.md` (session table of record)

Rule: do not propose changes that contradict `docs/PROJECT_STATE.md` without updating it in the same PR/commit.

## Canonical Surface Rules

- Always prefer canonical paths (see `docs/CANONICAL_PATHS.md`). New work must target canonical surfaces.
- Compatibility-only and legacy paths must not be revived as active product direction. They exist for transition, not investment.
- Obsolete host, runtime, or UI paths must be removed or clearly quarantined when no longer canonical. Do not preserve dead alternatives as if they are still viable.
- No new implementation wave may broaden backend or oracle scope unless it improves the felt player/library experience in the same or next wave.

## Governance-First Rule

Before any build/runtime/product modernization wave begins:

- update the authoritative docs first when roadmap/state/worklist/registry truth is changing
- do not start later-wave implementation until those docs agree on execution order and constraints
- treat documentation and agent-guidance alignment as a hard gate, not optional cleanup

## Coding Rules

- `pathlib.Path` always, never `os.path`
- `logging.getLogger(__name__)` always, never `print()`
- Parameterized SQL only (`?` placeholders)
- Type hints on all signatures; Google-style docstrings
- All runtime paths sourced from `oracle/config.py`
- `snake_case` for files/functions, `PascalCase` for classes, `UPPER_SNAKE` for constants
- Do not invent emotional dimensions beyond the fixed 10 listed above

## Key Modules

- `oracle/config.py` - environment-backed runtime config
- `oracle/db/schema.py` - migrations and `get_connection()`
- `oracle/scorer.py` - 10-dim CLAP scoring
- `oracle/acquirers/waterfall.py` - acquisition cascade
- `oracle/acquirers/guard.py` - pre/post acquisition validation
- `oracle/api/__init__.py` - Flask app factory
- `oracle/api/blueprints/` - API route handlers
- `oracle/player/` - canonical backend player domain
- `docs/CANONICAL_PATHS.md` - canonical vs compatibility vs legacy surface registry

## Build, Test, Validation

Run from repo root on Windows with `.venv` active.

```powershell
# Backend tests
python -m pytest -q

# Renderer tests + build
cd desktop\renderer-app
npm run test
npm run build

# Desktop smoke
powershell -ExecutionPolicy Bypass -File scripts\smoke_desktop.ps1 -AllowLlmFailure

# System health
python -m oracle doctor
python -m oracle status

# Docs QA
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session System Rules

Every behavior-changing session must:

1. Run `scripts/new_session.ps1` to open the session
2. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
3. Add or update one row in `docs/SESSION_INDEX.md`
4. Update `docs/PROJECT_STATE.md` if architecture/metrics/runtime truth changed
5. Update `docs/WORKLIST.md` if done/next work changed
6. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap was closed or discovered

Session ID format: `S-YYYYMMDD-NN`.

Commit prefix format: `[S-YYYYMMDD-NN] <type>: <description>`.

Start command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

## Parallel Lane Protocol

When multiple agents are working in parallel:

- read the root `AGENTS.md` first
- then read the most relevant lane brief under `docs/agent_briefs/`
- if two agents are sharing a wave, also read `docs/agent_briefs/tandem-wave-protocol.md`
- do not cross into another lane's files unless the active brief explicitly allows it
- if a task changes roadmap/state/worklist/registry or agent coordination, update docs first before implementation
- exactly one agent is the wave owner for any active wave
- the second agent must stay on a non-overlapping parallel lane with separately claimed files
- each agent opens its own session and records owned files plus forbidden files in the matching session log
- authoritative docs (`docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/SESSION_INDEX.md`) are reconciled only during an explicit sync window or by the wave owner

## Done Criteria

A task is done only when:

- `python -m pytest -q` passes
- if renderer changed: `npm run test` and `npm run build` pass
- `docs/PROJECT_STATE.md` reflects current truth
- a matching row exists in `docs/SESSION_INDEX.md`
- session log file exists in `docs/sessions/`
- `scripts/check_docs_state.ps1` passes

Code is not done if docs/state artifacts were skipped.
