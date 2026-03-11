# Worklist

Last updated: March 10, 2026 (updated same session)

## Execution Rule

Prioritize backend work that makes Lyra feel like a music-intelligence system, not just a competent local player.
Do not let UI polish or shell work outrun backend truth.

Use `docs/BACKEND_ACCEPTANCE_MATRIX.md` as the backend release gate.

## Priority Order

1. `G-060` Native acquisition parity
2. `G-066` Provider auth and transport autonomy
3. `G-064` Discovery graph and bridge depth
4. `G-063` Composer and playlist intelligence depth
5. `G-061` Explainability and provenance breadth
6. `G-065` Packaged desktop confidence

## Active Lane

### Backend Truth Hardening

- [x] Audit backend truth against the current Lyra/Cassette product promise
- [x] Create `docs/BACKEND_ACCEPTANCE_MATRIX.md`
- [x] Add backend verification for canonical junk rejection
- [x] Add backend verification for Spotify session persistence/refresh without UI dependency
- [x] Add backend verification for prompt-to-playlist draft generation from backend state
- [x] Add backend verification for evidence-bearing graph explainability
- [x] Add backend verification that EDM-drop prompts do not overclaim current capability
- [x] Add backend verification for provider transport cache fallback
- [x] Quarantine the legacy Python acquisition bridge so the canonical backend path is Rust-first
- [x] Add first-class album/discography acquisition planning with canonical release filtering
- [x] Add canonical Spotify authorization-code exchange and session bootstrap
- [x] Add a first lineage/member/offshoot backend baseline and use it in route and explanation logic
- [x] Add MusicBrainz artist intelligence ingestor (`artist_intelligence.rs`) — persists verified lineage edges beyond curated baseline
- [x] Add pure-Rust audio feature extraction (`track_audio_features.rs`) — RMS energy, peak, dynamic range, volatility, tag BPM/key
- [x] Expose lineage ingestor as Tauri commands (`ingest_artist_relationships`, `pending_artist_ingestion_count`, `get_lineage_ingest_status`) with `lineage_ingest_log` progress table — BA-10 Pass
- [x] Expose audio extractor as Tauri commands (`extract_audio_features_batch`, `pending_audio_extraction_count`, `get_audio_extraction_status`) with `audio_extraction_log` progress table — BA-13 Pass
- [x] Prove `audio_proof`-category evidence in `explain_track` after `upsert_features` (oracle test)
- [x] Prove verified lineage edges surface in `get_related_artists` after ingestor run (oracle test)
- [x] Add acquisition lifecycle state transition test (queued → validating → failed, honest failure fields)
- [x] Add 3-cycle bootstrap stability soak to `backend_runtime_confidence.rs`
- [ ] Run MB artist intelligence ingestion across full library (`ingest_artist_relationships` via Tauri or CLI)
- [ ] Run audio feature batch extraction across full library (`batch_extract`)
- [x] Wire `track_audio_features` rows into composer/explain evidence items — compound music-language claims in `oracle.rs::explain_track` via `build_audio_feature_evidence`
- [x] Add isolated app-data backend runtime confidence proof
- [ ] Run packaged clean-machine and long-session backend confidence proof
- [x] Wire yt-dlp as T4 fallback in native acquisition waterfall
- [x] Build 3-layer official variant backup validator (catalog + planning + audio_data)
- [x] Fix preflight to detect all native downloader tools (spotdl, streamrip, yt-dlp)
- [x] Prove native acquisition end-to-end: 18/18 tracks acquired, 13 files in A:\Music
- [x] Implement Zero-Touch daemon initialization with automatic slskd spawn on app boot
- [x] Wire acquisition queue auto-execution to Tauri setup handler
- [x] Implement tier-specific timeouts for waterfall (T1: 20s, T2: 40s, T3: 60s, T5: 30s, T4: 90s)
- [ ] Obtain slskd.exe binary and place in desktop/renderer-app/src-tauri/binaries/
- [ ] Populate .env with SOULSEEK_USERNAME and SOULSEEK_PASSWORD
- [ ] Test Zero-Touch end-to-end: Boot app → Daemon spawns → 811 items auto-acquire → Files to A:\Music
- [ ] Queue Brand New and Muse discographies and acquire them
