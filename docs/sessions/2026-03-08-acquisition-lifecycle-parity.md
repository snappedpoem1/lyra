# Session Log - S-20260308-12

**Date:** 2026-03-08
**Goal:** Implement Wave Y acquisition lifecycle parity across Rust, Tauri, UI, docs, and validation
**Agent(s):** Codex

---

## Context

The repo truth already claimed G-060 was effectively complete, but the live implementation still had material gaps:

- acquisition rows still used thin `pending` / `in_progress` semantics
- the Rust-owned queue lacked queue order, cancellation, worker/provider diagnostics, output-path ownership, and downstream completion flags
- the Tauri bridge did not emit a dedicated acquisition event stream
- the Svelte acquisition page was still primarily poll-driven
- queue completion could occur before organize/scan/index proved library availability
- `COPILOT_SYSTEM_PROMPT.md` still described Lyra as Python-primary

---

## Work Done

- [x] Expanded the canonical Rust acquisition model and SQLite migration path with explicit lifecycle states, queue order, timestamps, cancellation, provider/tier/worker metadata, output paths, structured failure fields, and downstream organize/scan/index completion flags.
- [x] Reworked the acquisition dispatcher so a queue item now progresses through `validating -> acquiring -> staging -> organizing -> scanning -> indexing -> completed`, and only finishes after the track is organized into a library root and imported into SQLite.
- [x] Added safe queue reordering and cancellation support, including cancel-request handling while the Python waterfall subprocess is active.
- [x] Added backend lifecycle callback plumbing from `lyra-core` through Tauri and exposed a dedicated `lyra://acquisition-updated` event payload for the frontend.
- [x] Upgraded the Svelte acquisition workspace into a real workflow surface with live event consumption, richer preflight checks, queue reordering/cancel actions, provider/tier visibility, downstream-stage visibility, and item-level diagnostics.
- [x] Extended waterfall JSON events with provider/tier/stage metadata so Rust can persist and surface the actual handling path.
- [x] Reconciled truth docs and agent guidance to match the real canonical runtime and the newly landed acquisition behavior.
- [x] Added Rust-owned validation confidence, first-pass guard checks, duplicate rejection, and taste-seeded priority scoring before queue items ever reach the Python waterfall.
- [x] Added per-item destination-root selection and persistence so organization is no longer hard-coded to the first accessible library root.
- [x] Tightened active cancellation by polling cancel requests independently of waterfall stdout activity, closing the quiet-subprocess cancellation gap.
- [x] Removed the hard `.venv` Python dependency for acquisition when native `qobuz` service, `streamrip`, `slskd`, or `spotdl` providers are available, while keeping the Python waterfall as a fallback for broader legacy tiers.

---

## Key Files Changed

- `crates/lyra-core/src/commands.rs` - expanded acquisition contract types, preflight checks, and event payload.
- `crates/lyra-core/src/db.rs` - added acquisition schema migration columns and legacy status normalization.
- `crates/lyra-core/src/acquisition.rs` - rebuilt queue persistence, lifecycle transitions, cancellation, and reorder semantics.
- `crates/lyra-core/src/acquisition_dispatcher.rs` - implemented end-to-end lifecycle follow-through, destination routing, duplicate validation, provider health accounting, and callback-driven updates.
- `crates/lyra-core/src/acquisition_worker.rs` - added worker callback support for live event propagation.
- `crates/lyra-core/src/lib.rs` - exposed new acquisition controls, richer preflight checks, Rust-owned guard/confidence/priority seeding, and callback-based processing entry points.
- `desktop/renderer-app/src-tauri/src/main.rs` - emitted canonical acquisition events and wired new Tauri commands.
- `desktop/renderer-app/src/lib/types.ts` - updated acquisition types for the Svelte frontend.
- `desktop/renderer-app/src/lib/tauri.ts` - added move/cancel/destination-root acquisition invocations.
- `desktop/renderer-app/src/lib/stores/lyra.ts` - consumed acquisition events to keep shell state honest.
- `desktop/renderer-app/src/routes/acquisition/+page.svelte` - rebuilt the acquisition workflow surface around live lifecycle data, destination control, and validation confidence.
- `oracle/acquirers/waterfall.py` - emitted richer phase/success/failure metadata for canonical lifecycle ownership.
- `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/ROADMAP_ENGINE_TO_ENTITY.md`, `COPILOT_SYSTEM_PROMPT.md` - reconciled truth and next-lane guidance.

---

## Result

Wave Y is materially implemented in the canonical runtime.

What is now true:

- acquisition items have an explicit lifecycle across validation, acquisition, staging, organize, scan, index, completion, failure, and cancellation
- lifecycle metadata is persisted in Rust-owned SQLite with queue order, timestamps, provider/tier/worker details, failure semantics, output paths, and downstream stage flags
- the frontend can observe live lifecycle updates from Tauri rather than relying on shell refreshes alone
- the acquisition page now exposes reorder, cancel, retry, clear, detailed diagnostics, preflight readiness, and downstream completion state
- the acquisition page now exposes destination-root selection and Rust-scored validation confidence alongside queue diagnostics
- acquisition completion now means the track has been moved into a configured library root and imported into the canonical library database

Remaining gap:

- deeper external metadata-validator parity and eventual reduction of the transitional Python waterfall bridge

---

## Validation

- [x] `cargo check --workspace`
- [x] `cargo test --workspace`
- [x] `cargo clippy --workspace --all-targets -- -D warnings`
- [x] `npm run check`
- [x] `npm run test`
- [x] `npm run build`
- [x] `cargo check --manifest-path desktop/renderer-app/src-tauri/Cargo.toml`
- [x] `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1`

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` updated

---

## Next Action

Continue with `G-061` by carrying provenance and confidence through saved playlist detail and broader recommendation explanation flows while preserving the new shell-integrated acquisition trust model.
