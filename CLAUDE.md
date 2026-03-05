# CLAUDE.md — Claude Code Persistent Memory for Lyra Oracle

> Claude Code reads this file automatically at session start.
> Keep it current. It is the single source of truth for Claude sessions.

---

## Read Order (Always Do This First)

1. This file (`CLAUDE.md`)
2. `AGENTS.md` — coding rules, key modules, build commands, session system
3. `docs/PROJECT_STATE.md` — audited facts about the running system
4. `docs/MISSING_FEATURES_REGISTRY.md` — real gaps
5. `docs/WORKLIST.md` — active cycle done/todo
6. `docs/SESSION_INDEX.md` — all session history

---

## What Lyra Is

Lyra Oracle is a local-first music intelligence system. Not a generic web app.

- Python 3.12, Flask API, SQLite (`lyra_registry.db`), ChromaDB (`chroma_storage/`)
- CLAP embeddings via DirectML (AMD GPU) on Windows
- 10-dimensional emotional scoring: `energy`, `valence`, `tension`, `density`, `warmth`,
  `movement`, `space`, `rawness`, `complexity`, `nostalgia`
- React 18 + TypeScript + Vite desktop renderer
- 5-tier acquisition waterfall: Qobuz → Streamrip → Slskd → Real-Debrid → SpotDL

---

## Current Truth (Last Audited: March 5, 2026)

| Metric | Value |
|---|---|
| Tracks indexed | 2,454 |
| Scored tracks | 2,454 |
| Embeddings | 2,454 |
| Graph connections | 1,815 |
| Spotify history rows | 127,312 |
| Playback events | 30,680 |
| Backend tests | 64 passed |

See `docs/PROJECT_STATE.md` for the full audited snapshot.

---

## Working Rules

- Trust code and local data over old docs.
- Do not write docs claiming a feature is missing without checking the repo first.
- Do not write docs claiming a feature is complete if the surface is only partially wired.
- Prefer repo-relative references in docs unless an absolute path is genuinely necessary.
- Treat exported conversations, old planning notes, and prototype folders as historical inputs, not live truth.

---

## Session State Requirements

When work materially changes the project state, Claude must update:

1. `docs/SESSION_INDEX.md` — append a row for this session
2. `docs/sessions/YYYY-MM-DD-<slug>.md` — create or update the session log
3. `docs/PROJECT_STATE.md` — if facts changed (metrics, modules, architecture)
4. `docs/WORKLIST.md` — if done/next items changed
5. `docs/MISSING_FEATURES_REGISTRY.md` — if a gap was closed or newly identified
6. `.claude/memory/MEMORY.md` — update working memory snapshot (legacy, keep in sync)
7. `.claude/memory/SESSIONS.md` — append the change (legacy, keep in sync)

**A session is not closed until these files are updated.**

---

## What "Done" Means

- `python -m pytest -q` → all tests pass
- If renderer touched: `npm run test` and `npm run build` pass in `desktop/renderer-app/`
- `docs/PROJECT_STATE.md` reflects current reality
- Session entry exists in `docs/SESSION_INDEX.md`
- Session log exists in `docs/sessions/`
- No broken relative Markdown links in tracked `.md` files

---

## State Sync Protocol

When you finish a session:

```
1. Run: python -m pytest -q
2. Summarize what changed (code, behavior, metrics)
3. Update docs/PROJECT_STATE.md if facts changed
4. Update docs/WORKLIST.md (move done items, add new next items)
5. Update docs/MISSING_FEATURES_REGISTRY.md if a gap status changed
6. Append to docs/SESSION_INDEX.md
7. Create docs/sessions/YYYY-MM-DD-<slug>.md
8. Commit with prefix: [S-YYYYMMDD-NN] <type>: <description>
```

---

## Legacy Memory Location

Historical Claude session state lives in `.claude/memory/`. Keep `.claude/CLAUDE.md` and
`.claude/memory/` in sync with this file when doing major state updates. The root `CLAUDE.md`
(this file) takes precedence for current truth.
