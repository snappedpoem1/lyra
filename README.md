# Lyra

Lyra is a desktop-first, playlist-first, local-first music intelligence and curation system.

The canonical runtime is:

- Tauri 2 shell
- SvelteKit frontend
- Rust application core
- SQLite local store

The canonical app runtime is Python-free, but the repo still contains valuable Python implementation that must inform migration of recommendation, enrichment, discovery, acquisition, and playlist-intelligence behavior.

## Why Lyra Exists

- Local ownership of taste and listening intelligence instead of dependence on opaque streaming feeds
- Explainable recommendation that tells the user why a track, artist, or bridge surfaced
- Playlist generation as authored journeys, not just shuffled buckets of tracks
- Discovery that goes beyond passive algorithm sludge through related-artist, bridge-track, and graph-style exploration

## Current Runtime

- Desktop shell: `desktop/renderer-app/src-tauri/`
- Frontend: `desktop/renderer-app/src/routes/`
- Rust core: `crates/lyra-core/`
- Local database: app-data SQLite owned by Rust

Legacy Python/oracle material is not part of normal startup, playback, queue, or library flow.
It remains an active migration source for already-solved process logic and feature behavior.

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

## What Works Now

- Tauri launches without a Python sidecar
- SvelteKit desktop shell renders and talks to Rust through Tauri commands
- Rust owns SQLite init, library roots, scan/import, playlists, queue, settings, and provider config records
- Native playback, session restore, repeat/shuffle, SMTC, tray/menu/global shortcuts, and window-state persistence are implemented
- Recommendation, taste profile, artist profile, and acquisition surfaces exist in the canonical app in partial form
- Provider import, provider validation, and secure secret storage hooks exist in the Rust/Tauri runtime

## What Is Still Missing

The runtime foundation is ahead of the product identity layer.
Lyra already behaves like a capable native local player, but its core differentiators are still incomplete or uneven in the canonical app:

- act and narrative playlist generation with durable reason payloads
- broad "why is this track here?" coverage across recommendation and playlist surfaces
- graph and constellation-style discovery depth
- visible provenance and confidence across enrichment and recommendation flows
- fuller dimensional and emotional scoring surfaces that users can actually inspect and act on
- migration of the strongest already-implemented Python intelligence workflows into Rust/Tauri/Svelte

## Legacy Logic And Migration Reality

The Python code in `oracle/` and `lyra_api.py` is not the canonical runtime.
It does still contain meaningful implemented logic for:

- acquisition waterfall behavior
- recommendation orchestration
- explainability and reason generation
- enrichment workflows
- graph/discovery process design
- taste memory and backfill
- curation and duplicate handling

Future work should port those solved behaviors deliberately.
Do not treat the repo as if those systems need to be invented from scratch.

## Configuration Reality

Provider and API configuration already exists in the repo and local environment.
Lyra already has configuration loaders, provider env mappings, provider config records, and safe secret-storage paths.
Future work should reuse and normalize that plumbing into the canonical runtime rather than replacing it with dummy examples or placeholder architecture.

Secret values are intentionally not documented here.

## Legacy Import

Lyra can import supported provider settings from `.env` and selected content from `lyra_registry.db` into the Rust-owned runtime store.

Imported now:

- supported provider/API keys
- tracks
- saved playlists where shape is compatible
- queue/session state where available

Preserved but not migrated now:

- Chroma/vector state
- Python enrich cache internals
- acquisition job history
- richer oracle feedback and reasoning internals not yet ported

## Docs

- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/ARCHITECTURE.md`
- `docs/MIGRATION_PLAN.md`
- `docs/CANONICAL_PATHS.md`
