# Session Log - S-20260309-01

**Date:** 2026-03-09
**Goal:** Deepen Lyra taste memory, adjacency routing, provider narrative obedience, and prototype-faithful testing shell
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

The canonical composer already had:

- action routing for playlist / bridge / discovery / explain / steer
- role-aware framing and fallback honesty
- steering controls in the renderer
- a very light taste-memory hook stored as recent steer strings in settings

The honest gap was still the same one called out in the March 8 sessions:

- taste memory was thin and not evidence-aware
- bridge and discovery routes were first-class structurally, but still close to improved local similarity logic
- provider-authored narrative was not fully constrained by the Lyra contract
- the playlists surface still read more like a composer panel than the intended Cassette workspace for evaluating Lyra

---

## Work Done

Bullet list of completed work:

- [x] Added persisted taste-memory tables plus typed session posture, remembered preference, and route-choice history structures
- [x] Replaced the settings-only memory hook with a real `taste_memory` module that records recent steer pressure without overclaiming certainty
- [x] Threaded taste-memory snapshots through app shell state and composer responses so the UI can render memory cues honestly
- [x] Extended bridge and discovery contracts with typed route variants, adjacency signals, and preserve/change explanations
- [x] Added safe / interesting / dangerous discovery variants and direct bridge / scenic / contrast bridge variants
- [x] Constrained provider-authored narrative behind a Lyra-specific system prompt and sanitizer so provider copy obeys role / fallback / route language better
- [x] Reworked the playlists route toward the prototype-shaped Cassette workspace with a stronger central Lyra composer, visible route comparison row, result canvas, and right-side reasoning/memory surface
- [x] Applied the Cassette shell / Lyra intelligence naming split in the shared shell and workspace copy
- [x] Ported the feasible legacy semantics from `oracle/arc.py` and `oracle/explain.py` into Rust: adjacent-swap transition optimization, dimension-distinctiveness reasons, taste-alignment evidence, and deeper local-history novelty/deep-cut phrasing
- [x] Ported additional feasible semantics from legacy graph/playlust behavior: graph-backed artist adjacency pressure in route scoring, playlust-style arc template shaping for playlist phases, and explicit accepted/rejected route feedback capture in Cassette
- [x] Updated truth docs and canonical behavior docs for taste memory, adjacency reasoning, provider narrative obedience, and Cassette branding
- [x] Validated `cargo check -p lyra-core`, `cargo test -p lyra-core`, `cargo clippy -p lyra-core --all-targets -- -D warnings`, `npm run check`, `npm run build`, and `cargo check --manifest-path desktop/renderer-app/src-tauri/Cargo.toml`

---

## Commits

| SHA (short) | Message |
|---|---|
| `xxxxxxx` | `S-20260309-01 type: description` |

---

## Key Files Changed

- `crates/lyra-core/src/commands.rs` - expanded typed intelligence and taste-memory contracts
- `crates/lyra-core/src/db.rs` - added taste-memory persistence tables
- `crates/lyra-core/src/intelligence.rs` - deepened route logic, provider narrative control, and framing integration
- `oracle/arc.py` - legacy sequencing reference consulted for swap-based transition optimization
- `oracle/explain.py` - legacy explainability reference consulted for dimension/taste/deep-cut reasoning patterns
- `crates/lyra-core/src/lib.rs` - wired taste-memory capture and shell exposure into runtime commands
- `crates/lyra-core/src/taste_memory.rs` - new taste-memory persistence and summarization module
- `desktop/renderer-app/src/lib/types.ts` - mirrored the expanded Rust contracts into the renderer
- `desktop/renderer-app/src/lib/stores/lyra.ts` - exposed shell taste-memory defaults
- `desktop/renderer-app/src/lib/stores/workspace.ts` - moved shell defaults to Cassette framing
- `desktop/renderer-app/src/routes/+layout.svelte` - applied Cassette shell branding and copy split
- `desktop/renderer-app/src/routes/playlists/+page.svelte` - rebuilt the composer surface into a prototype-faithful Lyra workspace
- `docs/PROJECT_STATE.md` - state update summary
- `docs/WORKLIST.md` - reprioritized remaining composer / adjacency gaps
- `docs/LYRA_INTELLIGENCE_CONTRACT.md` - documented taste memory, adjacency, and provider narrative obedience
- `docs/LYRA_VOICE_AND_PERSONA.md` - documented memory honesty and provider narrative boundaries
- `docs/LYRA_BEHAVIOR_EXAMPLES.md` - added a taste-memory-with-restraint example

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Yes, with an important honesty clause.

What is now true:

- Lyra has a real persisted taste-memory hook with session posture, rolling remembered preferences, route-choice history, and explicit recency/confidence notes
- bridge and discovery responses now carry typed route variants and adjacency language for safe / interesting / dangerous and direct / scenic / contrast logic
- route sequencing now uses a bounded arc-style transition optimizer and track reasons surface more specific local dimension and taste-alignment evidence
- route scoring now pulls on local artist-graph/co-play/genre adjacency when the prompt gives Lyra a source scene to work from
- playlist drafting now chooses from a small set of playlust-style arc shapes instead of one generic phase contour
- Cassette can now record accepted or rejected route lanes back into taste memory without pretending that one click equals a permanent preference
- provider-authored narrative is more tightly constrained by the Lyra contract instead of being a loose two-sentence helper
- the renderer now presents the composer inside a more truthful Cassette workspace that makes route comparison, memory cues, and explanation visible enough for product evaluation

What is still not true:

- this is not deep long-term personalization yet
- adjacency reasoning is stronger and more explicit, but it still stops short of a fully ported legacy semantic/graph stack

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass:
  - `cargo check -p lyra-core`
  - `cargo test -p lyra-core`
  - `cargo clippy -p lyra-core --all-targets -- -D warnings`
  - `npm run check`
  - `npm run build`
  - `cargo check --manifest-path desktop/renderer-app/src-tauri/Cargo.toml`

---

## Next Action

What is the single most important thing to do next?

Make taste memory learn from explicit accepted / rejected route choices and port stronger legacy adjacency evidence so route selection depends less on improved scoring alone.

