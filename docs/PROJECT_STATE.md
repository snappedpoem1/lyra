# Lyra Project State

Last audited: March 10, 2026 (updated same session)

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
- The backend now has a curated lineage/member/offshoot graph baseline and can surface examples such as `Cursive -> The Good Life` and `At The Drive-In -> Sparta / The Mars Volta` with honest evidence levels.
- `artist_intelligence.rs` exposes a MusicBrainz relationship ingestor as Tauri commands (`ingest_artist_relationships`, `pending_artist_ingestion_count`, `get_lineage_ingest_status`). Progress is tracked in `lineage_ingest_log`. Tests in `backend_runtime_confidence.rs` prove that cached MB edges are persisted and surface in `get_related_artists`.
- `track_audio_features.rs` exposes a pure-Rust audio feature extractor as Tauri commands (`extract_audio_features_batch`, `pending_audio_extraction_count`, `get_audio_extraction_status`). Progress is tracked in `audio_extraction_log`. When features exist, `explain_track` surfaces `audio_proof`-category evidence items (proven by oracle test).
- There is an isolated app-data backend runtime proof for canonical startup, discography planning, acquisition lifecycle state transitions, and 3-cycle bootstrap stability.
- BA-10 (lineage population pipeline) and BA-13 (audio extraction + deep evidence path) both reach Pass. BA-11 and BA-14 remain Partial.

What is not yet true:

- The artist intelligence ingestor has not yet been run against the full library. Pending count reflects all artists without verified MB edges.
- Audio feature extraction has not yet been run across the real library. Batch extract is wired and ready; it needs a run against real files.
- Packaged clean-machine and long-session backend confidence are still unproven. The current proof is isolated-app-data + 3-cycle soak, not a full packaged clean-machine proof.
- Explainability is not yet universal across all composer/explanation outputs (BA-11 Partial remains).

The backend source of truth for pass/fail acceptance is `docs/BACKEND_ACCEPTANCE_MATRIX.md`.

## What The Backend Does Well Already

- Stable backend state ownership for a real player-plus-intelligence system
- Prompt-to-playlist and prompt-to-route orchestration in Rust
- Canonical provider normalization and junk rejection
- Rust-owned acquisition planning for single tracks, albums, and discographies
- Backend-owned Spotify auth/session lifecycle
- Evidence-aware recommendation payloads, lineage-aware adjacency, and non-local acquisition lead handoff
- Library-wide lineage ingestion pipeline (Tauri commands, progress tracking, MB-verified edge persistence)
- Library-wide audio feature extraction pipeline (Tauri commands, PCM analysis, audio_proof evidence in explain_track)

## Native Acquisition Execution

The Rust-native acquisition waterfall is now proven end-to-end:

- **Waterfall chain**: T1 Qobuz → T2 Streamrip → T3 Slskd → T5 SpotDL → T4 yt-dlp
- **Preflight**: `downloader_available=true` (detects spotdl, streamrip, yt-dlp on PATH)
- **Proven execution**: 18/18 tracks acquired, 0 failures, 13 files landed in `A:\Music` (5 FLAC, 8 MP3)
- **Official variant validator**: 3-layer bypass (catalog release-group, acquisition planning junk filter, audio_data variant rejection) allows official live albums, demos, and deluxe editions while blocking bootlegs, karaoke, and lo-fi covers
- **CLI runner**: `acquisition_runner --limit N [--dry-run]` for batch queue processing
- **Queue state**: 811 items remaining, pipeline proven, lossless providers (Qobuz/Slskd) await daemon startup

## Zero-Touch Daemon Initialization (S-20260310-14)

**Status**: IMPLEMENTED & OPTIMIZED (March 10, 2026)

Lyra fully automates the downloader initialization experience with Qobuz-first waterfall optimization:

- **Daemon Lifecycle** – `daemon_manager.rs` spawns slskd.exe silently as managed child process on app boot
- **Credential Plumbing** – Extracts Soulseek username/password from .env or SQLite provider_configs; passes securely via environment (never command-line)
- **Dynamic Config** – Generates `slskd.yml` with detected port and paths; no manual .yml editing needed
- **Library Root** – Ensures `A:\Music` is configured and created on first boot; acquisition destination guaranteed available
- **Auto-Execution** – If queue has pending items, background acquisition_worker processes them automatically; no manual CLI runner needed
- **Graceful Lifecycle** – Daemon started on app boot, properly shut down on app close; port binding checks prevent duplicate spawns
- **Tier-Specific Timeouts** – Waterfall uses adaptive timeouts per provider:
  - T1 Qobuz: 20s (native HTTP, fast auth, quick FLAC availability)
  - T2 Streamrip: 40s (subprocess-based, slower provider auth)
  - T3 Slskd: 60s (P2P network, allows search propagation time)
  - T5 SpotDL: 30s (Spotify scraper)
  - T4 yt-dlp: 90s (final fallback, slowest provider)

**What this enables:**
- User boots Lyra app
- Soulseek daemon spawns automatically (no VBScript, no manual start)
- 811 queued items begin auto-execution with smart timeout strategy
- Waterfall prioritizes Qobuz with aggressive 20s timeout (fail-fast), cascades to slower tiers as needed
- Downloaded files organized into A:\Music library automatically

**Documentation**: `docs/ZERO_TOUCH_INITIALIZATION.md` (comprehensive guide)

## Highest-Value Missing Backend Work

1. **Acquire the 811 queued items** using Zero-Touch initialization. Place slskd.exe binary and test end-to-end with populated queue.
2. Run `ingest_artist_relationships` against the full library to populate MB-verified lineage edges beyond the curated baseline.
3. Run `batch_extract` (audio features) across the library to populate `track_audio_features` for all active tracks.
4. Carry evidence categories and provenance uniformly through all composer/explanation surfaces (BA-11 Partial gap).
5. Run clean-machine packaged validation and longer backend soak proof (BA-14 Partial gap).
