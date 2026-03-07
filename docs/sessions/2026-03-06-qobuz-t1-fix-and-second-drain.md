# Session Log - S-20260306-16

**Date:** 2026-03-06
**Goal:** Fix the Tier 1 Qobuz service URL runtime bug, validate the waterfall path, and run a second tiny bounded drain
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

Session `S-20260306-15` had already landed safe UI cleanup, queue
reprioritization, bounded enrichment, and a first tiny drain. That first drain
showed a real Tier 1 bug in the Qobuz path: `_download_via_service()` still
referenced an undefined legacy `QOBUZ_SERVICE_URL` symbol even though the rest
of the module used `_get_qobuz_config()`.

---

## Work Done

- Fixed the Tier 1 Qobuz service-path bug in `oracle/acquirers/qobuz.py` by
	resolving `service_url` from `_get_qobuz_config()` at call time instead of
	referencing the removed `QOBUZ_SERVICE_URL` global.
- Revalidated the backend suite after the fix:
	- `python -m pytest -q` → `106 passed`
- Ran a second tiny bounded drain:
	- `python -m oracle.cli drain --limit 1 --workers 1 --max-tier 4`
	- Tier 1 Qobuz succeeded for `Bear Hands - Agora` in `11.2s`
	- the acquired file was then rejected by ingest as a duplicate of an already
		owned local file (`Bear Hands - 2AM.flac`)
	- the queue item was re-queued as stale rather than falsely marked complete

---

## Commits

| SHA (short) | Message |
|---|---|
| `pending` | `[S-20260306-16] feat: fix qobuz tier1 runtime path` |
| `pending` | `[S-20260306-16] docs: record qobuz tier1 fix and second drain` |

---

## Key Files Changed

- `oracle/acquirers/qobuz.py` - fixed the Tier 1 service call to use the live
	configured `service_url`
- `docs/PROJECT_STATE.md` - recorded the verified Tier 1 fix and second drain
	outcome
- `docs/WORKLIST.md` - recorded the follow-up queue/drain proof
- `docs/SESSION_INDEX.md` - added session completion row

---

## Result

The Tier 1 Qobuz path no longer fails on an undefined service URL variable.
The second tiny drain proved that the waterfall can succeed on T1 again.

What is now true:

- Tier 1 Qobuz succeeds in the bounded drain path again
- the next real queue issue is duplicate-aware completion/requeue handling, not
	a broken T1 service call
- queue pending remains `2,434` after the duplicate rejection/requeue outcome

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Keep the release-gate priority intact, but when queue work resumes, make stale
duplicate acquisitions resolve cleanly instead of re-queuing forever after a
successful T1 download.

