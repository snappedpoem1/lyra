# Session Log - S-20260310-15

**Date:** 2026-03-10
**Goal:** Implement a real Prowlarr to Real-Debrid acquisition tier with seeder filtering and honest waterfall ordering
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

- Native acquisition execution had already been proven with the honest current chain still ending in yt-dlp.
- `acquisition_dispatcher.rs` had begun to drift toward a future Real-Debrid slot, but the actual Rust-native T4 executor did not exist yet.
- The legacy Python code under `archive/legacy-runtime/oracle/` already contained the working reference behavior for Prowlarr search, magnet normalization, seeder filtering, and Real-Debrid transfer orchestration.
- The goal of this session was to start porting that behavior honestly instead of pretending T4 already existed in the canonical Rust path.

---

## Work Done

- [x] Audited the canonical Rust acquisition dispatcher and the legacy Python Real-Debrid / Prowlarr implementation to identify the real port points.
- [x] Added Real-Debrid-oriented timeout constants and queue-aware seeder threshold helpers in `acquisition_dispatcher.rs`.
- [x] Added dispatcher scaffolding for Prowlarr candidate handling and provider mapping that treats T4 as `realdebrid` and pushes yt-dlp to T6 in naming.
- [ ] Finish the executable native Prowlarr search → Real-Debrid acquire path in the Rust dispatcher.
- [ ] Remove the remaining active yt-dlp fallback path once the T4 path is actually working.

---

## Commits

| SHA (short) | Message |
|---|---|
| `uncommitted` | `S-20260310-15 start honest Real-Debrid tier port` |

---

## Key Files Changed

- `crates/lyra-core/src/acquisition_dispatcher.rs` - added Real-Debrid timeout scaffolding, seeder threshold helpers, provider-tier remapping, and Prowlarr candidate structure groundwork
- `crates/lyra-core/src/waterfall.rs` - still participates in the tier-label consistency problem that must be cleaned up when the native T4 path lands
- `docs/sessions/2026-03-10-realdebrid-prowlarr-tier.md` - now records the session honestly as partial scaffolding rather than a blank template

---

## Result

The session did not complete the full Prowlarr → Real-Debrid port. What is now true is narrower and honest: the dispatcher has preparatory Real-Debrid constants and tier-mapping groundwork, but the canonical runtime still does not have a working native T4 executor and yt-dlp remains the effective fallback path.

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added as `S-20260310-15`
- [ ] Validation run for the unfinished T4 path

---

## Next Action

Implement the actual native Prowlarr search → Real-Debrid execution path, then remove or relabel the remaining yt-dlp fallback so the waterfall ordering is truthful end-to-end.

