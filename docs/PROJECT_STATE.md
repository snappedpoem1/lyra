# Lyra Project State

Last audited: March 8, 2026 — Wave W (Acquisition Provider Restoration)

## Runtime Truth

- Canonical runtime is now:
  - Tauri 2 desktop shell
  - SvelteKit SPA renderer
  - Rust application core in `crates/lyra-core`
  - Rust-owned SQLite local store
- Python is not part of canonical startup, playback, queue, library, or normal player operation.
- The old Python/oracle runtime remains preserved as legacy reference and migration source only.

## Implemented In This Pass

- Root Rust workspace created with `crates/lyra-core` and the Tauri app crate.
- `crates/lyra-core` now owns:
  - config paths
  - SQLite schema/init
  - library roots and scan jobs
  - track import and library queries
  - playlist persistence
  - queue persistence
  - playback state surface
  - settings persistence
  - provider config/capability registry
  - legacy `.env` and SQLite import path
- `desktop/renderer-app` is now a SvelteKit app with real views for:
  - Home
  - Library
  - Playlists
  - Queue / Now Playing
  - Settings
- Tauri host no longer launches a Python sidecar and instead invokes Rust-owned commands directly.
- Native desktop hooks implemented:
  - tray
  - menu
  - global shortcuts
  - window state persistence

## Implemented vs Scaffolded

Implemented:

- Python-free Tauri boot path
- direct Rust command bridge
- Rust-owned SQLite init
- library roots persistence
- file scan/import with lofty tag extraction (title, artist, album, duration from ID3/FLAC/MP4/Ogg tags; filesystem fallback)
- playlist CRUD + full editing (add/remove/reorder tracks, create from queue)
- queue persistence, reorder, remove, clear
- settings persistence
- provider config records and capability registry
- legacy `.env` and legacy DB import
- real rodio audio backend: `OutputStream` actor thread, `Sink` play/pause/seek/volume, `get_pos()` position tracking
- playback position ticker in Tauri: emits `lyra://playback-updated` every second while playing, auto-advances queue on track end (respects repeat-mode)
- seek enabled (`seek_supported: true`, `Sink::try_seek`)
- `+ Playlist` action in Library view (modal playlist picker)
- drag-to-reorder + remove in Playlist detail view
- `Save queue as playlist` action in Queue view
- session restore on relaunch: playback state normalized to `paused` on restart; cold-resume via `toggle_playback` re-seeks to saved position; `stop_playback` and `sync_playback_state` added to core
- stop-at-end: when `repeat_mode=off` and queue is exhausted, ticker transitions to `stopped` and persists state so it does not re-trigger
- Windows SMTC (System Media Transport Controls): taskbar/lock-screen media overlay wired via `ISystemMediaTransportControlsInterop`; button events drive core commands directly; track metadata (title/artist/album) and playback status updated each ticker tick
- audio device enumeration and selection: `cpal` direct dep enumerates output devices by name; `preferred_output_device` in settings persists across restarts; `list_audio_devices` and `set_output_device` Tauri commands wired
- SvelteKit settings page: audio device picker dropdown with system-default fallback; loads `AudioOutputDevice[]` on mount; calls `set_output_device` on selection change
- live MusicBrainz enrichment adapter: `MusicBrainzAdapter` (ureq HTTP, recording search endpoint) replaces the null stub in `EnrichmentDispatcher::default()`; cache-first via `enrich_cache` table; returns structured `recordingMbid`/`releaseMbid`/`matchScore`/`releaseDate` payload
- `enrich_track(track_id)` Tauri command exposed to the frontend via `LyraCore::enrich_track()`
- background enrichment on scan: after each `start_library_scan` completes, up to 30 unenriched tracks are dispatched via MusicBrainz at 1.1 s/request (rate-limit safe) in the scan background thread; uses `EnrichmentDispatcher::background()` (MusicBrainz + AcoustID only, no credential reads)
- `enrich_library` Tauri command: enriches up to 50 unenriched tracks on demand (UI button), fires-and-forgets in its own thread
- Library UI: "Enrich Library" button in the header; per-track ✧ toggle shows enrichment panel (MBID, release title, release date, match score, release MBID)
- `LastFmAdapter`: real Last.fm `track.getInfo` enrichment; reads `lastfm_api_key` from provider_configs; returns listeners, playcount, top tags (≤5), wiki summary; graceful `not_configured` when no key set
- `DiscogsAdapter`: real Discogs `/database/search` enrichment; reads `discogs_token` from provider_configs; returns year, genres, styles, label, country; authenticated or unauthenticated
- `EnrichmentDispatcher::new(conn)`: full 4-adapter dispatcher (MusicBrainz + AcoustID + LastFm + Discogs) for user-triggered enrichment; `background()` for background scan pass
- `refresh_track_enrichment(track_id)` Tauri command: clears enrich_cache for a track and re-dispatches full enrichment; Library UI has ↺ Refresh button in enrichment panel
- `validate_provider(provider_key)` Tauri command: lightweight credential probe returns `ProviderValidationResult { valid, latencyMs, error, detail }`; records provider health; Settings UI adds Validate button with inline ✓/✗ + latency
- Discogs + AcoustID added to `default_provider_capabilities()` seed; Discogs token added to `provider_env_mappings()`
- `RecommendationBroker::recommend_scored()`: returns `Vec<(track_id, score)>` ranked by cosine-similarity + overlap weighted score against taste profile; threshold 0.15
- `get_recommendations(limit)` Tauri command: resolves scored track IDs to `Vec<RecommendationResult { track, score }>` via `LyraCore::get_recommendations()`
- `explain_recommendation(track_id)` Tauri command: returns `ExplainPayload { reasons, confidence, source }` with human-readable taste match breakdown
- `ExplainPayload` + `RecommendationResult` added to `commands.rs` and wired to frontend types/bindings
- Discover page "For You" section: recommendation grid with match % bar, + Queue button, "Why?" toggle to show explanation panel; loads on demand, refreshable
- Shuffle mode in `play_next`: when `shuffle=true` picks a random queue index (time-based, != current) instead of sequential advance
- `repeat_mode="one"` in ticker: replays the just-finished track by calling `play_track(current_track_id)` instead of advancing or stopping
- `update_taste_from_completion()` in `taste.rs`: nudges taste profile dimensions 3% toward (completion>=0.5) or away (completion<0.1) from track's score vector after each playback event; called automatically from `record_playback_event`
- **Wave N/O**: `GeniusAdapter` (Genius API lyrics URL + artist enrichment), `LrcSidecarAdapter` (`.lrc` sidecar file), both wired into `EnrichmentDispatcher::new()` and surfaced in library enrichment panel
- **Wave O**: `keyring` crate v3 OS-level credential storage; `keyring_save/load/delete` Tauri commands; Settings UI has per-provider 🔐 Keychain and ↑ Load buttons
- **Wave P**: Qobuz `auth.getMobileSession` probe in `validate_provider`
- **Wave Q**: Taste profile visualization on Discover page (10-dim colored bar chart, reactive from `$shell.tasteProfile`)
- **Wave R**: Liked tracks — `liked_at TEXT` column on `tracks`; `toggle_like(track_id) -> bool`; `list_liked_tracks()`; Library view has ♥/♡ per-track button + "Liked" tab filter; Queue / Now Playing section has ♥ button on current track with optimistic update
- **Wave S**: Last.fm scrobbling — `scrobble.rs` module with `sign()` (md5-based), `scrobble()`, `now_playing()`, `get_mobile_session()`; fires automatically on `record_playback_event` when completion>=0.5; `now_playing` fires on `play_track`; Settings UI has Last.fm authentication form; `lastfm_get_session` stores session_key back into provider config
- **Wave T**: Sleep timer — `sleep_until: Arc<Mutex<Option<Instant>>>` in Tauri AppState; `set_sleep_timer(minutes)` / `get_sleep_timer()` commands; ticker loop checks and fires stop + emits `lyra://sleep-timer-fired`; Settings UI has timer form
- **Wave U/V**: Queue page ♥ button on now-playing track; Discover page "Recent plays" panel (last 20 playback events with timestamp + completion indicator, loads on demand)
- **Wave W**: Acquisition provider restoration:
  - All acquisition providers added to `default_provider_capabilities()`: Qobuz, Streamrip, SpotDL, Prowlarr, Real-Debrid, Slskd/Soulseek
  - Complete `provider_env_mappings()` for all acquisition providers with comprehensive credential support
  - Validation probes for all providers: Prowlarr (system/status), Real-Debrid (user endpoint), Slskd (session auth), Streamrip (binary check), SpotDL (Spotify OAuth), Spotify (client credentials), ListenBrainz (token validation), AcoustID (key format)
  - `acquisition_dispatcher.rs` module: Python waterfall bridge for tier-based acquisition (Qobuz → Streamrip → Prowlarr/RD → SpotDL)
  - `process_acquisition_queue()` in LyraCore: synchronous queue processor with retry logic (max 3 attempts), automatic library scan trigger on success
  - `process_acquisition_queue` Tauri command wired and exposed to frontend
  - `acquisition_worker.rs` module: Background worker thread-based polling (30s idle interval, 5s after processing)
  - `start_acquisition_worker()`, `stop_acquisition_worker()`, `acquisition_worker_status()` in LyraCore and Tauri
  - `diagnostics.rs` module: System health checks (database, Python, library roots, worker status) + statistics
  - `run_diagnostics()` Tauri command for comprehensive system health reporting
  - Acquisition UI page: Full queue management (add items, process manually, filter by status, retry failed items)
  - Background worker UI controls: Start/stop worker, status indicator (running/stopped), check status button
  - Settings page diagnostics panel: System health status, component checks, statistics grid, worker controls
  - UTF-8 BOM handling in .env parser (strips EF BB BF before dotenvy parse)
  - Base64 HTTP Basic auth helper for provider validation probes
  - All acquisition functions restored via Python waterfall subprocess delegation
  - Complete UI integration: diagnostics in Settings, worker controls in Settings + Acquisition pages
  - Base64 auth helper for HTTP Basic authentication in provider probes
  - UTF-8 BOM handling in `.env` file parsing (strips EF BB BF before dotenvy parse)
  - All acquisition functions restored via Python subprocess delegation (battle-tested waterfall preserved)
- **Wave X**: UI/runtime reconnection pass:
  - New canonical artist profile surface: `get_artist_profile` Rust API + Tauri command + `/artists/[name]` Svelte route
  - Artist links wired across Library, Queue, Discover, and now-playing transport metadata
  - Transport bar now includes shuffle and repeat controls (`off`/`one`/`all`) wired to Rust playback commands
  - Queue play actions now update playback state in both queue page and right queue panel
  - Discover page supports AI playlist generation from current recommendation results (creates playlist and adds top scored tracks)
  - Now-playing panel shows enrichment-derived artwork fallback and remains visible with viewport-fit shell sizing
  - Legacy parity port: native `play_artist` and `play_album` commands added and wired into artist page actions
  - Legacy/ChatGPT artifact sweep completed (including `C:\chatgpt` export); workflow-level parity needs captured in `docs/WORKFLOW_NEEDS.md`

Scaffolded / honest baseline:

- acquisition dispatcher delegates to Python for now; native Rust ports can follow incrementally
- AcoustID adapter is real (fpcalc shell-out) but fpcalc not yet installed on dev machine

## Boot Path

1. Tauri launches the desktop window.
2. Tauri initializes `LyraCore` with app-data directories.
3. Rust opens or creates the local SQLite database and seeds provider capability metadata.
4. SvelteKit bootstraps through Tauri commands, not HTTP.
5. Native tray/menu/shortcut W):

- `cargo check --workspace` EXIT:0
- `cargo clippy --manifest-path crates/lyra-core/Cargo.toml -- -D warnings` EXIT:0 (zero warnings)
- `cargo build --manifest-path crates/lyra-core/Cargo.toml` EXIT:0
- `cargo build --manifest-path desktop/renderer-app/src-tauri/Cargo.toml` EXIT:0
- env credential backup: 19 credentials saved to OS keychain

Not yet run:

- `npm run tauri build` (full release bundle with NSIS)
- blank-machine installer proof
- 4-hour audio soak
- end-to-end acquisition flow test

## Immediate Next Truth

Wave W complete (acquisition provider restoration). Remaining high-value targets:
- Test end-to-end acquisition flow: add item to queue → process → verify download → trigger scan
- Frontend UI for acquisition queue management (view pending/completed/failed items)
- `npm run tauri build` release bundle + blank-machine installer proof
- AcoustID: install `fpcalc` on dev machine and validate fingerprint round-trip
- Scrobble session auth UX: surface session key status in Settings
- 4-hour audio soak
- 4-hour audio soak

## Immediate Next Truth

Waves A–V are complete. Remaining high-value targets:
- `npm run tauri build` release bundle + blank-machine installer proof (Wave W)
- AcoustID: install `fpcalc` on dev machine and validate fingerprint round-trip
- Scrobble session auth UX: surface session key status in Settings (show whether session_key is present)
- 4-hour audio soak
- History panel track resolution: show artist/title instead of track # (requires join or a lookup on demand)
