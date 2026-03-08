# Worklist

Last updated: March 8, 2026

## Current State

- Rust/Tauri/SvelteKit is the active runtime path.
- Python/oracle runtime surfaces are preserved as legacy reference only.
- Wave W delivered: full acquisition provider restoration with Python waterfall bridge.
- Wave X delivered: artist profile route, now-playing transport controls (shuffle/repeat), queue-play state sync, AI playlist build from recommendations, and artist play/album commands.

## Completed Waves (this session)

- Wave W: Acquisition provider restoration
- Wave X: UI/runtime reconnection + artist/discovery parity pass
  - `get_artist_profile`, `play_artist`, `play_album` commands exposed in canonical runtime
  - `/artists/[name]` page with bio, related artists, top tracks, album actions
  - Artist links across Library, Queue, Discover, and now-playing transport
  - Transport controls for shuffle + repeat modes
  - Queue play actions now update playback state consistently
  - Discover can build an AI playlist from top recommendations

## Next Up

1. Implement acquisition lifecycle UX states from `docs/WORKFLOW_NEEDS.md` (acquire -> stage -> scan -> organize -> index)
2. Add enrichment confidence/provenance and MBID-first rendering in Library + Artist views
3. Implement curation workflow (duplicate review/apply + cleanup preview)
4. Add run-based playlist intelligence with persisted reason payloads
5. Run `npm run tauri build` release bundle with NSIS installer
6. Blank-machine validation on clean Windows VM
7. 4-hour audio soak

## Deferred But Explicit

- Arc sequencing (track journey builder)
- Agent/Architect (LLM-powered workflows)
- Chroma/vector migration to Rust
- Full oracle/recommendation parity beyond current recommendation core
- Installer/release hardening once runtime workflows stabilize
