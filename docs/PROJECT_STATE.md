# Lyra Project State

Last audited: March 10, 2026

## Canonical Runtime Truth

Lyra's canonical runtime remains:

- Tauri 2 desktop shell
- SvelteKit renderer
- Rust core in `crates/lyra-core`
- Rust-owned SQLite local store

Python is not part of the intended canonical runtime.
The canonical backend acquisition path is now Rust-first.
Legacy Python acquisition remains only as an explicit migration bridge behind `LYRA_ENABLE_LEGACY_ACQUISITION_BRIDGE`.

## Backend Reality

The backend is real and useful, but it does not yet fully satisfy the Lyra/Cassette product promise.

What is already true:

- Rust owns the core state model for library, playlists, queue, playback state, provider config, acquisition queue state, discovery sessions, composer runs, and taste memory.
- The backend can generate playlist drafts, bridge routes, discovery routes, steer revisions, and explanation responses from prompts plus backend state.
- Provider-fed track payloads normalize into a canonical backend shape, and obvious junk variants are rejected before canonical persistence.
- Rust now owns single-track, album, and discography acquisition planning with canonical catalog filtering and persisted plan state.
- Provider transport, config validation, Spotify auth bootstrap/exchange, session persistence, and refresh behavior exist in Rust and are no longer frontend-only concerns.
- Recommendation and explain surfaces emit evidence-bearing payloads with evidence categories and grades, and discovery can hand non-local leads into acquisition.
- The backend now has a first curated lineage/member/offshoot graph baseline and can surface examples such as `Cursive -> The Good Life` and `At The Drive-In -> Sparta / The Mars Volta` with honest evidence levels.
- There is now an isolated app-data backend runtime proof for canonical startup and discography planning outside repo-root assumptions.

What is not yet true:

- Broad lineage/influence ingestion is still missing. The current lineage graph is a curated backend baseline, not a complete artist-intelligence corpus.
- Deep vibe claims such as `mind-blowing EDM drops` are still heuristic. The backend can be honest about that, but it does not yet have a dedicated proof path.
- Packaged clean-machine and long-session backend confidence are still unproven. The current proof is isolated-app-data backend runtime confidence, not a full packaged soak.

The backend source of truth for pass/fail acceptance is `docs/BACKEND_ACCEPTANCE_MATRIX.md`.

## What The Backend Does Well Already

- Stable backend state ownership for a real player-plus-intelligence system
- Prompt-to-playlist and prompt-to-route orchestration in Rust
- Canonical provider normalization and junk rejection
- Rust-owned acquisition planning for single tracks, albums, and discographies
- Backend-owned Spotify auth/session lifecycle
- Evidence-aware recommendation payloads, lineage-aware adjacency, and non-local acquisition lead handoff

## Highest-Value Missing Backend Work

1. Replace the remaining optional migration bridge with a fully native acquisition executor proof path end to end.
2. Expand lineage/member/influence intelligence beyond the curated baseline into a broader backend graph source.
3. Carry evidence categories and provenance uniformly through all composer/explanation surfaces.
4. Deepen audio-feature-backed evidence so strong vibe claims are backed by more than score heuristics.
5. Run clean-machine packaged validation and longer backend soak proof.
