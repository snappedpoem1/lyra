# Architecture

## Overview

Lyra is a native desktop player built from:

- Tauri 2 host
- SvelteKit SPA frontend
- Rust core crate
- embedded SQLite

There is no canonical Python runtime path and no localhost backend dependency.

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
- legacy import path

## Data Flow

1. frontend invokes Tauri command
2. Tauri command calls `LyraCore`
3. `LyraCore` reads/writes SQLite and updates runtime state
4. Tauri emits domain events when state changes
5. frontend store updates and rerenders

## SQLite Model

Primary tables:

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

## Capability Migration Model

Wave 1 keeps the runtime player-first while establishing Rust-owned extension surfaces for:

- provider registry/config
- enrichment contracts
- acquisition contracts
- oracle/recommendation contracts

Those modules exist now so future parity work extends the Rust core rather than reviving Python sidecars.

