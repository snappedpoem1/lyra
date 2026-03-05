# Session Index

This file is the table of record for all Lyra Oracle work sessions.

**One row per session.** Every session that changes behavior must add a row here.
See `docs/sessions/_template.md` for the session log format.
See `AGENTS.md` -> Session System Rules for the full protocol.

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
| S-20260305-02 | 2026-03-05 | Codebase integrity pass - crashes, connection leaks, acquisition pipeline, batch perf | Multi-session | `oracle/worker.py`, `oracle/acquirers/waterfall.py`, `oracle/acquirers/guard.py`, `oracle/acquirers/realdebrid.py`, `oracle/acquirers/spotdl.py`, `oracle/acquirers/ytdlp.py`, `oracle/acquirers/qobuz.py`, `oracle/acquirers/streamrip.py` (new), `oracle/scorer.py`, `oracle/radio.py`, `oracle/normalizer.py`, `oracle/vibes.py`, `oracle/ingest_watcher.py`, `oracle/api/blueprints/acquire.py` | Fixed 3 critical crashes + 15 connection leaks + acquisition pipeline correctness + batch scoring/chaos perf; 64 tests green | Consolidate title normalizers (G-033); install librosa (G-032) |
| S-20260305-03 | 2026-03-05 | Check latest logs and continue pending work | `[S-20260305-03]` | `oracle/embedders/clap_embedder.py`, `tests/test_clap_embedder_audio_loading.py`, `scripts/new_session.ps1` | Audited logs, fixed audio loader failures (ZeroDivisionError/NoBackendError class), repaired session bootstrap script; pytest now 66 green | Re-run a bounded ingest/index pass and confirm previous audio-load failures do not recur |
