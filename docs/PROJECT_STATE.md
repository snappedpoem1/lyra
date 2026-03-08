# Lyra Project State

Last audited: March 8, 2026 (America/New_York)

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
- background enrichment on scan: after each `start_library_scan` completes, up to 30 unenriched tracks are dispatched via MusicBrainz at 1.1 s/request (rate-limit safe) in the scan background thread
- `enrich_library` Tauri command: enriches up to 50 unenriched tracks on demand (UI button), fires-and-forgets in its own thread
- Library UI: "Enrich Library" button in the header; per-track ✧ toggle shows enrichment panel (MBID, release title, release date, match score, release MBID)

Scaffolded / honest baseline:

- acquisition contracts are declared in Rust but not fully ported
- AcoustID, Discogs, LastFm enrichment adapters remain null stubs
- oracle/recommendation contracts are declared in Rust but not fully ported

## Boot Path

1. Tauri launches the desktop window.
2. Tauri initializes `LyraCore` with app-data directories.
3. Rust opens or creates the local SQLite database and seeds provider capability metadata.
4. SvelteKit bootstraps through Tauri commands, not HTTP.
5. Native tray/menu/shortcut wiring binds to Rust command handlers.

## Legacy Status

- `oracle/`, `lyra_api.py`, and Python-sidecar scripts are no longer canonical runtime paths.
- `desktop/renderer-app/legacy/react_renderer_reference/` preserves the old React renderer as reference.
- Legacy artifacts such as `.env`, `lyra_registry.db`, and `chroma_storage/` are preserved and not overwritten.

## Validation Snapshot

Validated in this pass:

- `cargo check --workspace` EXIT:0
- `cargo clippy --workspace --all-targets -- -D warnings` EXIT:0 (zero warnings)
- `cargo test --workspace` EXIT:0
- `cargo build --manifest-path desktop/renderer-app/src-tauri/Cargo.toml` EXIT:0
- `cd desktop/renderer-app; npm run check` EXIT:0 (0 errors, 0 warnings)
- `cd desktop/renderer-app; npm run build` EXIT:0 (renderer static bundle)
- App launches: `lyra_tauri.exe` runs, SMTC bridge initialises

Not yet run:

- `npm run tauri build` (full release bundle with NSIS)
- blank-machine installer proof
- 4-hour audio soak

## Immediate Next Truth

The repo is aligned around Rust/Svelte/Tauri as the single active runtime direction. The next wave should harden session-restore/resume semantics, add taskbar/media-session hooks, expand native integration, and begin porting provider and enrichment/oracle systems into the Rust-owned capability surfaces.

