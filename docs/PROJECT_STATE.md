# Lyra Project State

Last audited: March 8, 2026

## Canonical Runtime Truth

Lyra's canonical runtime is:

- Tauri 2 desktop shell
- SvelteKit SPA renderer
- Rust application core in `crates/lyra-core`
- Rust-owned SQLite local store

Python is not part of canonical startup, playback, queue, library, or normal app operation.
Legacy Python and oracle code remain in-repo as migration-source logic.

## Product Reality

Lyra is not blocked on becoming a native desktop app.
The active challenge is product identity depth: making the canonical app feel like Lyra instead of a competent local player.

Current product framing:

- Lyra is a vibe-to-journey intelligence and discovery system with native playback
- the composer is the front door
- playback, acquisition, provenance, and provider plumbing are support infrastructure

## Implemented Now

- Python-free canonical runtime boot path
- Rust-owned playback, queue, playlists, settings, provider config records, and local DB state
- acquisition workflow and horizon intelligence infrastructure
- enrichment provenance and confidence surfaces
- related-artist and graph scaffolding
- first real composer slice in the canonical runtime:
  - typed `PlaylistIntent`
  - local/cloud LLM provider abstraction
  - explicit provider selection and fallback mode in settings
  - deterministic retrieval, reranking, and sequencing in Rust
  - first-class composer action routing: draft, bridge, discovery, explain, steer
  - visible playlist phases and bridge/discovery route surfaces in the Svelte UI
  - steering controls for obviousness, adventurousness, contrast, warmth/nocturnal bias, and explanation depth
  - role-aware response behavior for recommender, coach, copilot, and oracle modes
  - track-level reason payloads
  - saved reason payload persistence in `playlist_track_reasons`
  - weird-prompt evaluation coverage for action classification and deterministic fallback honesty

## Still Missing

The current composer slice is foundational, not complete.
Major gaps remain:

- stronger prompt-to-discovery coverage outside playlist drafting
- deeper bridge-track and adjacency reasoning beyond the current first-class route scaffolding
- richer explanation coverage across saved playlists, discovery, and recommendation surfaces
- stronger local-LLM and cloud-LLM provider breadth and credential ergonomics
- more explicit taste steering, memory, and feedback loops
- broader migration of legacy semantic search, graph, and explainability behavior into Rust

## Current Priority Order

1. `G-063` Composer and playlist intelligence depth
2. `G-064` Discovery graph and bridge depth
3. `G-061` Explainability and provenance breadth
4. `G-060` Remaining acquisition runtime risk
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

This order is deliberate:

- composer and discovery are product identity
- explainability must stay close behind them
- acquisition remains important but is infrastructure
- package polish is a release gate, not the mission

## Configuration And Credential Reality

Provider and API configuration already exists in the repo and local environment.
This is not a blank configuration project.

Grounded facts:

- Rust persists provider config records in SQLite
- provider capability metadata already exists in Rust
- provider validation hooks already exist in Rust
- OS keyring support already exists in Rust
- the new composer pipeline reuses this provider config path for local/cloud LLM selection

Do not expose secrets in docs, logs, or summaries.
