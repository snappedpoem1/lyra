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

## Highest-Value Missing Backend Work

1. Run `ingest_artist_relationships` against the full library to populate MB-verified lineage edges beyond the curated baseline.
2. Run `batch_extract` (audio features) across the library to populate `track_audio_features` for all active tracks.
3. Carry evidence categories and provenance uniformly through all composer/explanation surfaces (BA-11 Partial gap).
4. Run clean-machine packaged validation and longer backend soak proof (BA-14 Partial gap).
5. Replace the remaining optional migration bridge with a fully native acquisition executor proof path end to end.
