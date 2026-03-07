# Session Log - S-20260306-18

**Date:** 2026-03-06
**Goal:** Resolve duplicate-backed successful acquisitions cleanly in the queue, validate with a tiny drain, and push the fix
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

- Tier 1 Qobuz was healthy again after `S-20260306-16`, but a real bounded drain showed that successful duplicate-backed acquisitions could still come back as stale queue rows.
- The immediate repro was `Bear Hands - Agora`, where Qobuz matched and downloaded `Bear Hands - 2AM`, ingest rejected that file as a duplicate of an existing library track, and the queue item later aged into `stale downloaded row re-queued by watcher reconciliation`.
- The gap was not in Qobuz itself; it was in post-flight correlation between a downloaded staging file and the queue row that produced it.

---

## Work Done

Bullet list of completed work:

- [x] Added path-correlated queue resolution in `oracle/cli.py` and `oracle/ingest_watcher.py` by preserving the staging path on `downloaded` rows and using it during duplicate handling.
- [x] Implemented duplicate-aware watcher resolution that completes true duplicate hits immediately and re-queues mismatch cases immediately with an explicit `duplicate acquisition mismatch` error.
- [x] Added focused regression coverage in `tests/test_ingest_watcher_queue_resolution.py` for exact-match completion, missing-track fallback, and mismatch retry behavior.
- [x] Validated with `python -m pytest -q` (`109 passed`) and a bounded live drain of `Bear Hands - Agora` that no longer fell into stale watcher re-queue behavior.

---

## Commits

| SHA (short) | Message |
|---|---|
| local only | not committed yet |

---

## Key Files Changed

- `oracle/cli.py` - preserves a temporary downloaded-path marker on queue rows so post-flight ingest can resolve the exact row it is processing
- `oracle/ingest_watcher.py` - uses that marker to complete exact duplicate hits or immediately retry mismatch cases with explicit errors
- `tests/test_ingest_watcher_queue_resolution.py` - covers exact-match and mismatch duplicate resolution behavior
- `docs/PROJECT_STATE.md` - records the new queue behavior and updated backend test count
- `docs/WORKLIST.md` - updates the queue follow-up status to resolved/improved behavior

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Duplicate-backed post-flight queue handling is no longer dependent on the 45-minute stale-row reconciliation path. When ingest rejects a downloaded file as a duplicate, Lyra now resolves the exact `downloaded` queue row immediately: exact matches are completed with the library track, and mismatches are re-queued immediately with a specific error explaining what was requested versus what was actually acquired.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

What is the single most important thing to do next?

Run the blank-machine installer proof, then return to the 4-hour parity soak while watching for any remaining acquisition mismatch patterns that should feed back into source ranking.

