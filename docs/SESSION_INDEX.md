# Session Index

This file is the table of record for all Lyra Oracle work sessions.

**One row per session.** Every session that changes behavior must add a row here.
See `docs/sessions/_template.md` for the session log format.
See `AGENTS.md` → Session System Rules for the full protocol.

---

## Format

| Session ID | Date | Goal | Commits | Key Files | Result | Next Action |
|---|---|---|---|---|---|---|
| `S-YYYYMMDD-NN` | YYYY-MM-DD | What was the goal | Commit SHAs or message prefixes | Files that changed most | What happened | What should happen next |

---

## Sessions

| Session ID | Date | Goal | Commits | Key Files | Result | Next Action |
|---|---|---|---|---|---|---|
| S-20260305-01 | 2026-03-05 | Establish agent session tracking system | Initial setup | `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/SESSION_INDEX.md`, `docs/sessions/_template.md`, `scripts/new_session.ps1` | Created agent memory files, session index, template, and automation script | Run `scripts/new_session.ps1` to start the next session |
