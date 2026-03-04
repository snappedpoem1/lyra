# SESSIONS.md — Lyra Oracle Change Log

> **Agents: Append a block here after every batch of changes.**
> Format: `## SESSION — YYYY-MM-DD` with what was built, fixed, and verified.

---

## SESSION — 2026-03-04

**Agent:** GitHub Copilot (cloud agent)
**Task:** Create agent memory/reference files; commit and push current project state.

### Changes Made
- Created `.claude/memory/` directory
- Created `.claude/memory/MEMORY.md` — live system state, metrics, what works/broken, next priorities
- Created `.claude/memory/SESSIONS.md` — this file (change log for all sessions)

### Why
CLAUDE.md and AGENTS.md both reference these memory files at startup, but the files did not exist in the repo. Agents were instructed to read them but had nothing to read.

### System State at Time of Session
- tracks: 2,472 | embeddings: 2,472 | track_scores: 2,472
- acquisition_queue: 0 pending (23,192 total processed)
- playback_history: 0 (playback bridge not yet connected)
- Layers 1–4 healthy; Docker services OK; LM Studio OK
- Frontend: unified dark-blue + lime CSS design system committed
- OracleDiscoveryPanel and DimensionalSearchPanel wired in frontend

### Next Priority
Connect foobar2000 + BeefWeb playback bridge so `playback_history` begins populating.

---

## SESSION — 2026-02-27 (pre-existing, reconstructed from CLAUDE.md)

**Agent:** Previous session (Claude / VS Code agent)
**Task:** Multiple feature and infrastructure improvements.

### Changes Made
- Unified CSS design system: removed dual amber/blue conflict, single dark-blue + lime aesthetic
- Added OracleDiscoveryPanel (`desktop/renderer-app/src/features/oracle/OracleDiscoveryPanel.tsx`)
- Refactored DimensionalSearchPanel
- Updated artist route, home route, oracle route
- Updated API blueprints: discovery.py, intelligence.py, radio.py, vibes.py
- Added `oracle/discover.py` (294 lines)
- Improved `oracle/radio.py` (radio modes: Chaos, Flow, Discovery)
- Updated `oracle/explain.py`
- Added `.claude/AGENTS.md` — agent review guidelines
- Added `.claude/CLAUDE.md` — project instructions (expanded from copilot-instructions.md)

### Verified
- Pipeline end-to-end: scan → index → score (2,472/2,472)
- 5-tier acquisition waterfall operational
- Qobuz FLAC acquisition with full metadata
- `oracle drain` auto-ingests (embed + score)

---

*Add new entries at the TOP of this file (below the header), not at the bottom.*
