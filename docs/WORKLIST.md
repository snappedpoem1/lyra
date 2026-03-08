# Worklist

Last updated: March 8, 2026 (Wave Y checkpoint)

## Current State

- Rust/Tauri/SvelteKit is the active runtime path.
- Python/oracle runtime surfaces are preserved as legacy reference only.
- Wave W delivered: full acquisition provider restoration with Python waterfall bridge.
- Wave X delivered: artist profile route, now-playing transport controls (shuffle/repeat), queue-play state sync, AI playlist build from recommendations, and artist play/album commands.
- Wave Y delivered (checkpoint): acquisition lifecycle visibility + controls (retry/clear/prioritize/preflight).

## Completed Waves (this session)

- Wave W: Acquisition provider restoration
- Wave X: UI/runtime reconnection + artist/discovery parity pass
  - `get_artist_profile`, `play_artist`, `play_album` commands exposed in canonical runtime
  - `/artists/[name]` page with bio, related artists, top tracks, album actions
  - Artist links across Library, Queue, Discover, and now-playing transport
  - Transport controls for shuffle + repeat modes
  - Queue play actions now update playback state consistently
  - Discover can build an AI playlist from top recommendations
- Wave Y: Acquisition workflow parity checkpoint
  - Lifecycle fields persisted per queue item (`lifecycle_stage`, `lifecycle_progress`, `lifecycle_note`, `updated_at`)
  - Lifecycle visualization in Acquisition UI (stage label + progress bar + note)
  - Queue controls implemented: retry failed, clear completed/skipped, set priority
  - Preflight checks exposed in UI: Python availability, downloader availability, disk-space threshold
  - Retry semantics fixed: failed -> pending increments `retry_count`, clears stale error/completed timestamp, resets lifecycle seed
  - Known contention: stage transitions are best-effort while core acquisition remains delegated to Python waterfall subprocesses

## Next Up (Prioritized by Impact)

Execution details for all waves are tracked in `docs/EXECUTION_PLAN.md`.

### Wave Y: Acquisition Workflow Parity (G-060) - HIGH PRIORITY
**Goal**: Complete end-to-end acquisition visibility and controls
- [x] Add staged lifecycle states (acquire → stage → scan → organize → index)
- [x] Implement per-item progress and error state UI
- [x] Add queue lifecycle controls:
  - Retry failed items
  - Clear completed items
  - Prioritize items
- [x] Add preflight checks:
  - Disk space validation before processing
  - Downloader/tool availability checks
- [x] Surface lifecycle events in Acquisition UI
- [ ] Close remaining contention: replace best-effort subprocess lifecycle transitions with authoritative phase events from waterfall or native Rust pipeline

### Wave Z: Enrichment Provenance & Confidence (G-061) - HIGH PRIORITY
**Goal**: Make enrichment sources and confidence transparent
- [ ] Add confidence scoring to enrichment results
- [ ] Display source provenance in Library and Artist views
- [ ] Promote `artist_mbid` and `recording_mbid` to first-class UI fields
- [ ] Add explicit enrichment lifecycle states (not_enriched, enriching, enriched, failed)
- [ ] Implement force re-enrich with source selection
- [ ] Show MBID-first identity information prominently

### Wave AA: Curation Workflows (G-062) - MEDIUM PRIORITY
**Goal**: Safe, reviewable library curation
- [ ] Duplicate resolution workflow:
  - Cluster review interface
  - Choose keeper UI
  - Quarantine/delete duplicates action
  - Undo capability
- [ ] Filename/path cleanup workflow:
  - Preview changes before apply
  - Show operation summary
  - Confirm before execution
- [ ] Organization plans:
  - Dry-run curation plan generator
  - Store rollback metadata
  - Safe apply with logging

### Wave AB: Playlist Intelligence Parity (G-063) - MEDIUM PRIORITY
**Goal**: Restore act-based playlist generation with explanations
- [ ] Implement act/narrative playlist generation:
  - Generate by intent/mood/journey
  - Explicit phases/acts structure
  - Track-level reason payloads
- [ ] Persist reason payloads in database
- [ ] Add "Why is this track here?" UI display
- [ ] Build save/apply flow for generated playlists
- [ ] Add playlist run history

### Wave AC: Discovery Graph Depth (G-064) - MEDIUM PRIORITY
**Goal**: Deeper graph-based discovery
- [ ] Artist graph inspection UI:
  - Visualize related-artist edges
  - Show connection strength/type
- [ ] Add "Play Similar" actions from artist graph
- [ ] Add "Queue Bridge" actions (cross-genre transitions)
- [ ] Surface discovery mode provenance (show source)
- [ ] Implement session memory:
  - Track recent interactions
  - Feed into next recommendations
  - Show to user in Discover

### Wave AD: Packaged Desktop Confidence (G-065) - RELEASE GATE
**Goal**: Production-ready installer and stability
- [ ] Run `npm run tauri build` release bundle with NSIS installer
- [ ] Blank-machine validation on clean Windows VM
- [ ] 4-hour audio soak test
- [ ] Long-session stability validation
- [ ] Installer cleanup and error handling
- [ ] Auto-update mechanism

## Quick Wins (Can be done anytime)

- [ ] Install `fpcalc` on dev machine and validate AcoustID fingerprint round-trip
- [ ] Add session key status display to Last.fm settings
- [ ] Show artist/title in history panel instead of just track IDs
- [ ] Add keyboard shortcuts documentation to Settings
- [ ] Implement "Recently Added" library filter
- [ ] Add bulk operations to Library (select multiple tracks)

## Deferred But Documented

- Arc sequencing (track journey builder with narrative flow)
- Agent/Architect (LLM-powered playlist generation and curation)
- Chroma/vector migration to Rust (move embeddings from Python)
- Extended oracle features beyond current recommendation core
- Multi-platform support (macOS, Linux)
- Cloud backup/sync capability
- Mobile companion app
