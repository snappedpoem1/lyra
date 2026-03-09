# Lyra

Lyra is a vibe-to-journey music intelligence, discovery, and curation system with native playback.

The canonical runtime is:

- Tauri 2 shell
- SvelteKit frontend
- Rust application core
- Rust-owned SQLite local store

Playback, queue, library, acquisition, and provider plumbing matter, but they are support systems.
Lyra’s differentiators are:

- freeform intent interpretation through the Lyra composer
- explainable recommendation and playlist authorship
- bridge-track and related-artist discovery
- taste steering and memory
- provenance-aware, confidence-aware intelligence

## Canonical Product Shape

Lyra is not:

- a generic media player
- a playback-first shell with an AI panel
- a local Spotify clone

Lyra is:

- a desktop-first music intelligence system
- a playlist-first discovery and curation product
- a smart music companion that interprets creative language as musical direction

The canonical intelligence rules live in [docs/LYRA_INTELLIGENCE_CONTRACT.md](docs/LYRA_INTELLIGENCE_CONTRACT.md).

## Current Runtime

- Desktop shell: `desktop/renderer-app/src-tauri/`
- Frontend: `desktop/renderer-app/src/routes/`
- Rust core: `crates/lyra-core/`
- Local database: Rust-owned app-data SQLite

Legacy Python and oracle code remain in-repo as migration-source logic for solved workflows.
They are not part of canonical startup, playback, queue, or library ownership.

## Current Intelligence Slice

The canonical app now includes a first-pass composer pipeline:

- typed `PlaylistIntent`
- local/cloud LLM provider abstraction with explicit fallback reporting
- deterministic retrieval, reranking, and sequencing in Rust
- visible playlist phases in the UI
- track-level reason payloads and saved reason persistence
- settings support for provider preference

This is the first real composer slice, not the finished Lyra vision.

## Quick Start

```powershell
cd desktop\renderer-app
npm install
npm run check
npm run build
npm run tauri:dev
```

Rust validation from repo root:

```powershell
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
```

## Docs Of Truth

- `AGENTS.md`
- `docs/LYRA_INTELLIGENCE_CONTRACT.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- `docs/MISSING_FEATURES_REGISTRY.md`
