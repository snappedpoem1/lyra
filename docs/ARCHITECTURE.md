# Architecture

## Overview

Lyra uses a native desktop architecture so it can own the full intelligence loop locally:

- Tauri 2 host
- SvelteKit SPA frontend
- Rust core crate
- embedded SQLite

This architecture is not only a Python replacement exercise.
It exists to support a self-owned music intelligence and curation system with native playback as one capability inside that product.

There is no canonical Python runtime path and no localhost backend dependency.

## Product-Capability View

The architecture is responsible for delivering these product capabilities:

- local playback and library stewardship
- explainable recommendation
- playlist generation and authored sequencing
- taste memory and dimensional scoring
- enrichment with provenance and confidence
- graph and bridge discovery
- acquisition and ingest workflows

## Runtime Layers

### Tauri shell

- owns native window lifecycle
- owns tray/menu/global shortcut integration
- exposes the Rust command surface to the frontend
- emits app events back to SvelteKit

### Svelte frontend

- owns layout and route/view structure
- calls Tauri commands directly
- listens to app events for queue/playback/library/provider updates
- renders the persistent desktop shell
- must surface Lyra's intelligence layer visibly instead of acting as a thin player shell only

### Rust core

- config and app paths
- SQLite migrations/init
- library roots and scan jobs
- tracks/albums/artists
- playlists
- queue/session state
- playback surface
- settings
- provider configs and capability registry
- enrichment
- recommendation and taste contracts
- acquisition and diagnostics
- legacy import path

## Data Flow

1. frontend invokes Tauri command
2. Tauri command calls `LyraCore`
3. `LyraCore` reads/writes SQLite and updates runtime state
4. Tauri emits domain events when state changes
5. frontend store updates and rerenders

That same flow should eventually carry:

- reason payloads
- provenance and confidence metadata
- graph/discovery state
- taste-memory signals
- authored playlist structure

## SQLite Model

Primary tables already support the runtime baseline and should continue expanding to support the intelligence layer:

- `artists`
- `albums`
- `tracks`
- `library_roots`
- `scan_jobs`
- `playlists`
- `playlist_items`
- `queue_items`
- `session_state`
- `settings`
- `provider_configs`
- `provider_capabilities`
- `migration_runs`

Future schema work should be framed around product capabilities, not only migration buckets:

- reason payload storage
- provenance/confidence fields
- graph edge storage
- taste/session memory
- curation operation logs
- acquisition lifecycle evidence

## Migration-Source Rule

Python is not the runtime, but it still contains meaningful migration-source logic.
Before implementing a product capability in Rust:

1. inspect whether Python already solved the workflow or provider sequence
2. preserve the useful behavior and semantics
3. avoid re-inventing process design that already exists in `oracle/`

Important migration-source areas include recommendation, explainability, enrichment, graph/discovery, acquisition orchestration, curation, and taste memory.

## Configuration Rule

Existing env/config/provider plumbing is already present in both Python and Rust surfaces.
Future architecture work should normalize and reuse it:

- Python `.env` loaders and repo-root config resolution
- Rust `provider_env_mappings()` and provider config import
- SQLite `provider_configs`
- Rust validation and keyring support

Do not build parallel config systems when the repo already has working configuration patterns.
