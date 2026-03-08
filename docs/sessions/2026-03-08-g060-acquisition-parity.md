# Session Log - S-20260308-08

**Date:** 2026-03-08
**Goal:** Harden canonical docs and implement G-060 acquisition workflow parity in Rust/Tauri/Svelte
**Agent(s):** Codex

---

## Context

The canonical runtime docs had drifted.
`codex.md` still described Lyra as a Python/Flask/React/Vite application, while the docs of truth already declared Tauri, SvelteKit, Rust, and SQLite as canonical.

The priority order also drifted.
Some truth files still elevated other identity work ahead of the requested acquisition-first lane, and the legacy-to-canonical port rule was implicit instead of explicit.

In the current working tree, canonical G-060 work was already partially present:

- lifecycle fields and queue controls existed in Rust
- the acquisition UI already showed queue rows and progress bars
- the Python waterfall bridge had been modified to emit structured phase events

The remaining gaps for this session were:

- normalize the authoritative docs
- lock the required priority order
- make the legacy-port rule explicit
- finish the missing G-060 workflow pieces that still weakened trust and visibility

---

## Work Done

- [x] Rewrote `codex.md` around the canonical Tauri/SvelteKit/Rust/SQLite runtime and removed stale Python-first framing.
- [x] Normalized `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, and `docs/MISSING_FEATURES_REGISTRY.md` so they clearly distinguish canonical truth, legacy migration truth, implemented now, partial/scaffolded work, and next priority work.
- [x] Locked the required execution order:
  1. `G-060` Acquisition workflow parity
  2. `G-061` Enrichment provenance and confidence
  3. `G-063` Playlist intelligence parity
  4. `G-064` Discovery graph depth
  5. `G-062` Curation workflows
  6. `G-065` Packaged desktop confidence
- [x] Added the explicit Legacy-to-Canonical Port Rule to `codex.md` and mirrored that rule in `docs/PROJECT_STATE.md`, `docs/MIGRATION_PLAN.md`, and `docs/MISSING_FEATURES_REGISTRY.md`.
- [x] Inspected the legacy acquisition sources before changing canonical behavior:
  - `oracle/acquisition.py`
  - `oracle/acquirers/smart_pipeline.py`
  - `oracle/acquirers/waterfall.py`
- [x] Extended canonical G-060 queue control behavior with a bulk retry-failed path in Rust and Tauri.
- [x] Hardened canonical acquisition preflight so it reports disk state plus transitional tool readiness more honestly:
  - Python venv presence
  - waterfall bridge presence
  - downloader tool presence on PATH (`spotdl`, `rip`, `slskd`)
- [x] Rebuilt the Svelte acquisition workspace into a live operator surface with:
  - summary cards
  - worker control
  - bulk retry
  - explicit prioritize/defer controls
  - lifecycle-event feed derived from queue changes
  - timed refresh while the worker or in-progress items are active
- [x] Fixed two stale example binaries so `cargo test --workspace` could pass against the current `list_tracks(query, sort)` signature.

---

## Legacy Source Mapping

### Acquisition lifecycle and queue semantics

- `oracle/acquisition.py`
  - informed retry-count behavior and queue-state transitions
- `oracle/acquirers/smart_pipeline.py`
  - informed queue ordering and retry/reject semantics
- `oracle/acquirers/waterfall.py`
  - informed staged lifecycle emission and transitional waterfall authority

### Canonical targets updated

- `crates/lyra-core/src/acquisition.rs`
- `crates/lyra-core/src/lib.rs`
- `desktop/renderer-app/src-tauri/src/main.rs`
- `desktop/renderer-app/src/lib/tauri.ts`
- `desktop/renderer-app/src/routes/acquisition/+page.svelte`

---

## Key Files Changed

- `codex.md` - canonical runtime truth, product dream, priority order, and legacy-port rule
- `docs/PROJECT_STATE.md` - implemented now vs partial, current priority order, legacy-port rule
- `docs/WORKLIST.md` - active canonical lane reset to the required order
- `docs/MISSING_FEATURES_REGISTRY.md` - gap IDs normalized to `G-060` through `G-065` with legacy sources called out
- `docs/MIGRATION_PLAN.md` - explicit legacy-to-canonical port rule added
- `docs/LEGACY_MIGRATION_REGISTRY.md` - porting rule tightened to require source recording
- `crates/lyra-core/src/acquisition.rs` - bulk retry-failed queue operation
- `crates/lyra-core/src/lib.rs` - stronger acquisition preflight and bulk retry entry point
- `desktop/renderer-app/src-tauri/src/main.rs` - Tauri command for retry-failed acquisition
- `desktop/renderer-app/src/lib/tauri.ts` - renderer binding for retry-failed acquisition
- `desktop/renderer-app/src/routes/acquisition/+page.svelte` - live acquisition workspace with lifecycle event feed and queue controls
- `crates/lyra-core/examples/configure_tauri_app.rs` - fixed stale `list_tracks` call
- `crates/lyra-core/examples/test_playback.rs` - fixed stale `list_tracks` call

---

## Validation

Executed successfully:

- `cargo check --workspace`
- `cargo test --workspace`
- `cd desktop\renderer-app; npm run check`
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1`

Validation notes:

- `cargo test --workspace` initially failed on stale example binaries using the old `list_tracks(None)` signature; those calls were updated to `list_tracks(None, None)`.
- `cargo test --workspace` now passes.
- `cargo check --workspace` and `cargo test --workspace` still report pre-existing warnings in `crates/lyra-core/src/playlists.rs` for unused variables `space`, `density`, and `nostalgia`.

---

## Result

The docs of truth are now aligned around the canonical runtime, the required execution order, and the explicit legacy-to-canonical port rule.

For G-060, the canonical acquisition workspace now supports:

- staged lifecycle visibility
- per-item progress and error display
- retry failed items in bulk
- clear completed items
- explicit prioritization controls
- stronger preflight checks
- surfaced lifecycle events in the UI

This session does not claim broader feature completion outside the G-060 lane.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row updated
- [x] Session log updated
- [x] Canonical validation run and recorded honestly

---

## Next Action

Start `G-061`: enrich canonical Library and Artist surfaces with provider provenance, confidence, and MBID-first identity visibility by porting the strongest existing legacy enrichment evidence semantics.
