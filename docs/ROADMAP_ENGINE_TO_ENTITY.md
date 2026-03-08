# Lyra Roadmap

Last updated: March 8, 2026

## Mission Lock

Lyra is a desktop-first, playlist-first, local-first music player.

Canonical runtime:

- Tauri 2 shell
- SvelteKit frontend
- Rust application core
- SQLite local store

Legacy Python/oracle material is preserved only as reference and migration source.

## Decision Lock

1. No Python in canonical startup, playback, queue, library, or settings flow.
2. No localhost backend dependency.
3. Rust owns runtime state, DB, library, queue, playback surface, provider configs, and native integration.
4. SvelteKit owns the active UI layer.
5. Future intelligence work must extend the Rust core instead of reviving sidecars.

## Current Milestone

Wave 1 is landed locally:

- Rust workspace and core crate created
- Tauri host converted away from the Python sidecar
- SvelteKit desktop shell created
- Rust-owned SQLite schema and command surface created
- library roots, scan jobs, playlists, queue, settings, provider config import, and native hooks implemented

## Next Waves

### Wave 2 - Playback hardening

- replace the wave-1 playback stub with real Rust audio output
- preserve the command surface while improving session restore

### Wave 3 - Library and playlist depth

- richer metadata extraction
- better import quality
- playlist editing and sequencing

### Wave 4 - Provider migration

- provider validation
- secure secret handling
- first live acquisition provider ports

### Wave 5 - Enrichment migration

- metadata provider ports
- score/analysis ports that improve the player experience

### Wave 6 - Oracle migration

- recommendation and playlist-intelligence systems on Rust-owned contracts
- reintroduction of explainable intelligence on the stable player baseline

### Wave 7 - Release confidence

- packaged desktop hardening
- installer validation
- deeper native integration
