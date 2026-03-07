# Session Log - S-20260306-15

**Date:** 2026-03-06
**Goal:** Land safe Mantine UI cleanup, fix queue prioritization, run bounded enrichment, and drain a tiny queue slice while soak validation continues
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

Session `S-20260306-14` was already occupying the soak and packaged-runtime
hardening lane, so this work stayed deliberately outside runtime, sidecar, and
parity-script changes. The open safe lanes were remaining Mantine cleanup,
bounded enrichment depth work, and queue operations that could proceed without
invalidating the soak evidence path.

---

## Work Done

- Extended the Mantine foundation into the remaining high-visibility legacy UI
	surfaces touched in this slice:
	- `desktop/renderer-app/src/features/oracle/OracleModeSwitch.tsx`
	- `desktop/renderer-app/src/app/routes/searchRoute.tsx`
	- `desktop/renderer-app/src/features/search/SearchHero.tsx`
	- `desktop/renderer-app/src/app/routes/artistRoute.tsx`
- Fixed the acquisition queue prioritizer to use the live
	`acquisition_queue.priority_score` column instead of the removed legacy
	`priority` column so bounded reprioritization and worker-driven drain can run
	again.
- Ran bounded enrichment and discovery passes while the soak lane continued:
	- `oracle.cli credits enrich --limit 15`
	- `oracle.cli structure analyze --limit 15`
	- `oracle.cli discover listenbrainz --limit-artists 80 --tracks-per-artist 8`
	- `oracle.cli graph similarity-edges --limit-artists 40 --top-k 10 ...`
- Reprioritized the top 500 pending queue items after the prioritizer fix.
- Drained a tiny queue slice (`oracle.cli drain --limit 2 --workers 1 --max-tier 4`):
	- 1 item succeeded via streamrip and was ingested/indexed/scored
	- 1 item failed and was re-queued for retry

---

## Commits

| SHA (short) | Message |
|---|---|
| `f0a67ca` | `[S-20260306-15] feat: land parallel ui and queue slice` |
| `pending` | `[S-20260306-15] docs: record parallel ui and queue enrichment state` |

---

## Key Files Changed

- `desktop/renderer-app/src/features/oracle/OracleModeSwitch.tsx` - replaced
	the custom mode toggle with Mantine `SegmentedControl`
- `desktop/renderer-app/src/app/routes/searchRoute.tsx` - replaced the custom
	search mode toggle with Mantine `SegmentedControl`
- `desktop/renderer-app/src/features/search/SearchHero.tsx` - moved the search
	input/button pair onto Mantine `TextInput` and `Button`
- `desktop/renderer-app/src/app/routes/artistRoute.tsx` - moved the route's
	loading/empty states, chips, actions, and stats scaffolding onto Mantine
	primitives without changing runtime behavior
- `oracle/acquirers/taste_prioritizer.py` - fixed queue reprioritization and
	batch selection to use `priority_score`
- `docs/PROJECT_STATE.md` - recorded updated queue and enrichment metrics plus
	the new queue/discovery activity
- `docs/WORKLIST.md` - recorded the completed safe parallel slice while release
	gate work continues elsewhere
- `docs/MISSING_FEATURES_REGISTRY.md` - updated graph/credits/structure evidence

---

## Result

The renderer now has fewer legacy UI surfaces in the active Search, Oracle,
and Artist paths, the acquisition queue can be taste-prioritized again, and
safe background work materially moved while the soak lane stayed untouched.

What is now true:

- queue reprioritization succeeds for live pending items
- ListenBrainz discovery added 136 new acquisition candidates
- `track_structure` grew from 159 to 172 analyzed tracks in this bounded run
- a tiny real queue drain succeeded for 1 track and re-queued 1 failed attempt
- the current pending queue rose to 2,434 after new discovery plus the tiny
	drain outcome

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `python -m pytest -q`

---

## Next Action

Keep the release-gate priority intact: finish the blank-machine installer proof
and complete the 4-hour parity soak, then return to larger graph/credits/
structure expansion if the soak lane stays green.

