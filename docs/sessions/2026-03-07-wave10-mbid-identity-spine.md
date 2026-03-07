# Session Log - S-20260307-11

**Date:** 2026-03-07
**Goal:** MBID Identity Spine: store recording MBIDs on tracks, enrich credits via MBID, add release-group/artwork context, optional live-orbit evidence
**Agent(s):** GitHub Copilot

---

## Context

Wave 9 was complete and pushed (`5c39396`). Library had 2,455 active tracks but only 4 recording_mbids and 0 release_group_mbids. `CreditMapper.map_batch()` had a column-name bug (`musicbrainz_id` does not exist on tracks — should be `recording_mbid`) making the MBID-backed credit path broken. Credits path was falling back to fuzzy MB search which returns 0 credits for most tracks.

---

## Work Done

- [x] Wrote `docs/specs/SPEC-010_MBID_IDENTITY_SPINE.md` covering batch resolver contract, DB columns, CLI design, credit_mapper fix, and test contract
- [x] Created `oracle/enrichers/mb_identity.py` — `MBIdentityResolver` class with `resolve_batch(limit, min_confidence, only_missing)` and `stats()`, two `ResolveResult` and `MBIDStats` dataclasses
- [x] Fixed `oracle/enrichers/credit_mapper.py` `map_batch()` — replaced `musicbrainz_id` with `recording_mbid` and added `status = 'active'` filter
- [x] Added `oracle mbid resolve` and `oracle mbid stats` CLI subcommands to `oracle/cli.py`
- [x] Wrote `tests/test_mb_identity.py` (13 tests: happy path, only_missing skip, no_match, exception resilience, stats)
- [x] Full test suite: 201 passed (was 188)
- [x] Launched 200-track MBID resolve pass against live MB API (~4 min, background job)
- [x] Updated `docs/PROJECT_STATE.md` with Wave 10 state
- [x] Updated `docs/MISSING_FEATURES_REGISTRY.md` G-031 to reflect fix

---

## Commits

| SHA (short) | Message |
|---|---|
| `pending` | `[S-20260307-11] feat: Wave 10 MBID identity spine` |

---

## Key Files Changed

- `oracle/enrichers/mb_identity.py` — new module: MBIdentityResolver batch MBID resolver
- `oracle/enrichers/credit_mapper.py` — fixed map_batch() column bug (musicbrainz_id → recording_mbid)
- `oracle/cli.py` — added `mbid resolve` and `mbid stats` subcommands
- `tests/test_mb_identity.py` — new: 13 contract tests for resolver + stats
- `docs/specs/SPEC-010_MBID_IDENTITY_SPINE.md` — spec (created)
- `docs/PROJECT_STATE.md` — Wave 10 state added
- `docs/MISSING_FEATURES_REGISTRY.md` — G-031 updated

---

## Result

Wave 10 MBID Identity Spine is landed. The library has a working batch resolver that populates `recording_mbid`, `artist_mbid`, `isrc` from MusicBrainz text search (confidence-gated at 0.65). Once the resolve pass completes, `CreditMapper.map_batch()` can be used for MBID-based credit lookup (the column bug is now fixed). Test suite grew from 188 to 201.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated — G-031
- [x] `docs/SESSION_INDEX.md` row already added by new_session.ps1
- [x] Tests pass: `python -m pytest -q` → 201 passed

---

## Next Action

Wave 11: Companion Pulse. After MBID resolve pass completes, run `oracle credits enrich --limit 500` to validate MBID-backed credit population. Then open Wave 11 session.

