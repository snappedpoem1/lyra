# Session Log - S-20260310-09

**Date:** 2026-03-10
**Goal:** Audit backend truth, add backend acceptance matrix, strengthen backend verification, and sync docs to code truth
**Agent(s):** Codex

---

## Context

The repo docs and instruction files were broadly aligned on product direction, but they overstated backend completeness in a few important places.
The main contradictions found during the audit were:

- the canonical runtime docs were closer to `fully Rust-owned acquisition` than the code really is
- backend provider auth/session claims were stronger than the actual backend bootstrap paths
- discovery/intelligence docs were more optimistic than the current lineage and deep-audio-evidence implementation

`AGENTS.md` remains the authoritative agent instruction file.
`codex.md`, `CLAUDE.md`, and `COPILOT_SYSTEM_PROMPT.md` are supportive but not primary.

---

## Work Done

- [x] Audited canonical docs and backend Rust surfaces for code-vs-doc truth
- [x] Confirmed that `crates/lyra-core/src/acquisition_dispatcher.rs` still prefers the legacy Python waterfall when available
- [x] Confirmed that first-class album/discography acquisition is still missing from the canonical Rust backend
- [x] Confirmed that lineage/member intelligence is still missing from the canonical graph/recommendation path
- [x] Fixed `explain_track` graph-evidence lookup to match the current SQLite schema
- [x] Enabled native Windows keyring support for the Rust `keyring` dependency so provider-token persistence matches the documented intent
- [x] Added backend tests for Spotify session persistence/refresh behavior without UI dependency
- [x] Added backend tests for canonical junk rejection, prompt-to-draft generation, graph-backed explainability, EDM-drop honesty, and provider cache fallback
- [x] Added `docs/BACKEND_ACCEPTANCE_MATRIX.md`
- [x] Synced `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, and `docs/MISSING_FEATURES_REGISTRY.md` to code truth

---

## Commits

| SHA (short) | Message |
|---|---|
| `uncommitted` | `[S-20260310-09] docs: record backend verification matrix truth pass` |

---

## Key Files Changed

- `crates/lyra-core/Cargo.toml` - enabled Windows-native keyring backend
- `crates/lyra-core/src/providers.rs` - added backend-owned Spotify session tests and stabilized shared keyring test state
- `crates/lyra-core/src/audio_data.rs` - added canonical junk-rejection test and tightened payload persistence signature
- `crates/lyra-core/src/provider_runtime.rs` - added cache-fallback transport verification
- `crates/lyra-core/src/intelligence.rs` - added honesty guard for overclaimed EDM/drop prompts and a direct prompt-to-draft backend test
- `crates/lyra-core/src/oracle.rs` - fixed explainability graph query against the current schema and added regression coverage
- `crates/lyra-core/src/acquisition.rs` - reduced tuple complexity in Spotify library import path
- `crates/lyra-core/src/enrichment.rs` - switched normalized payload persistence to typed raw-candidate input
- `docs/BACKEND_ACCEPTANCE_MATRIX.md` - new backend acceptance source of truth
- `docs/PROJECT_STATE.md` - compressed and corrected backend truth
- `docs/WORKLIST.md` - refocused worklist around backend truth gaps
- `docs/MISSING_FEATURES_REGISTRY.md` - corrected gap status to match code reality

---

## Result

The backend now has a grounded acceptance matrix and stronger automated proof for the parts it already does well.
The repo also states the current backend truth more honestly:

- prompt-to-playlist, bridge/discovery routing, canonical provider normalization, evidence-bearing recommendation payloads, and backend-owned Spotify session refresh are real
- native-only acquisition, album/discography acquisition, lineage intelligence, and strong audio-evidence-backed vibe claims are not yet done

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `cargo test -p lyra-core`
- [x] Lints pass: `cargo clippy -p lyra-core --all-targets -- -D warnings`

---

## Next Action

Remove the Python-first acquisition path and replace it with a native-only backend execution path before claiming canonical acquisition parity.
