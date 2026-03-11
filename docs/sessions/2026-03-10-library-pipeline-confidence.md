# Session Log - S-20260310-12

**Date:** 2026-03-10
**Goal:** Reset the corrupted local library state, harden metadata hygiene for discography planning, and probe a clean rebuild starting with Coheed and Cambria plus Brand New
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

- The user reported severe local-library corruption: altered metadata, wrong-song substitutions, and frequent instrumental/lofi/karaoke contamination.
- Cassette's live runtime database still pointed at a populated `A:\Music` root, so the rebuild had to begin with a destructive local reset.
- Rust-native discography planning already existed, but the first live probe still pulled in demo/bootleg/live junk and the helper bin itself was easy to misuse.
- Acquisition preflight on this machine was not downloader-ready: the canonical Rust path could plan work, but no supported native downloader tool was available on `PATH`.

---

## Work Done

- [x] Deleted the contents of the configured local library root and wiped the live Cassette catalog/acquisition state so the rebuild started from an empty library and empty queue.
- [x] Tightened catalog/planning hygiene to reject demo, soundcheck, acoustic, bootleg-event, instrumental, karaoke, and lofi contamination more consistently.
- [x] Fixed false positives in the classifier so legitimate songs like `Mix Tape` and `When Skeletons Live` are no longer rejected just because they contain bare words like `mix` or `live`.
- [x] Added a safer `discography_probe` Rust bin flow with `--help`, `--reset-acquisition-state`, explicit preflight output, and blocked-item reporting.
- [x] Re-ran the clean probe for `Coheed and Cambria` and `Brand New`, verified the queue was free of the targeted junk patterns, and recorded the remaining honest blocker: no supported native downloader tool is currently available on this machine.

---

## Commits

| SHA (short) | Message |
|---|---|
| `uncommitted` | `S-20260310-12 local rebuild + metadata hygiene hardening` |

---

## Key Files Changed

- `crates/lyra-core/src/bin/discography_probe.rs` - added a repeatable rebuild/probe helper with help output, queue reset, preflight reporting, and blocked-item visibility
- `crates/lyra-core/src/catalog.rs` - expanded release/track filtering so bootleg-event, demo, soundcheck, acoustic, instrumental, and lofi catalog entries stop entering the acquisition plan
- `crates/lyra-core/src/acquisition_planning.rs` - strengthened queue-time junk rejection for altered versions and added regression coverage for discography planning
- `crates/lyra-core/src/classifier.rs` - replaced overly broad bare-token rejection with more contextual live/remix/special variant detection
- `crates/lyra-core/src/audio_data.rs` - rejected plain lofi variants during canonical provider-track normalization
- `crates/lyra-core/src/validator.rs` - extended deterministic text validation to reject lofi/soundcheck/instrumental/karaoke variant titles
- `docs/SESSION_INDEX.md` - recorded the corrected session entry and live probe outcome

---

## Result

- Cassette's live library state is empty again, with `A:\Music` retained as the configured root for rebuilding in place.
- Discography planning for the two requested seed artists is materially cleaner: the original dirty probe produced `366+` queued rows; the cleaned rerun produced `207` queued rows total (`141` Coheed and Cambria, `66` Brand New) with only three blocked tracks, all legitimate non-canonical variants:
  - `Dark Side of Me (Einziger and Sanchez Remix)`
  - `Bought a Bride (live in studio)`
  - `I Will Play My Game Beneath the Spin Light (Live, Acoustic)`
- No queued rows matched the targeted junk patterns (`karaoke`, `lofi`, `lo-fi`, `instrumental`, `soundcheck`, `demo`, `acoustic`) after the final rerun.
- The current Rust codebase still does not have an active native Real-Debrid executor: T4 is named in tier mapping and provider config, but there is no native dispatch implementation and no `prowler` dependency in the current Rust path.
- The local blocker is now explicit and inspectable: acquisition preflight remains `ready=false` because no supported downloader tool (`qobuz-service`, `spotdl`, `rip`, or `slskd`) is available on this machine.

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added/updated
- [x] Focused Rust tests and live probe checks passed

---

## Next Action

Enable or implement one honest Rust-native downloader path so the cleaned discography queue can actually repopulate `A:\Music` instead of stopping at planning.
