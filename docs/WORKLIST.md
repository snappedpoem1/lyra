# Worklist

Last updated: March 8, 2026

## Current State

- Rust/Tauri/SvelteKit is the active runtime path.
- Python/oracle runtime surfaces are preserved as legacy reference only.
- Waves A–V delivered: Complete player, enrichment, recommendations, liked tracks, scrobbling, sleep timer, recent plays.
- Wave W delivered: Full acquisition provider restoration with Python waterfall bridge.

## Completed Waves (this session)

- Wave W: Acquisition provider restoration  
  - All providers added to capabilities (Qobuz, Streamrip, SpotDL, Prowlarr, Real-Debrid, Slskd)
  - Complete env mappings with comprehensive credential support
  - Validation probes for all providers (Prowlarr, Real-Debrid, Slskd, Streamrip, SpotDL, Spotify, ListenBrainz, AcoustID)
  - `acquisition_dispatcher.rs` module (Python waterfall bridge)
  - `acquisition_worker.rs` module (background thread-based polling)
  - `diagnostics.rs` module (system health checks + statistics)
  - `process_acquisition_queue()` command with retry logic
  - `start_acquisition_worker()`, `stop_acquisition_worker()`, `acquisition_worker_status()` commands
  - `run_diagnostics()` command for system health reporting
  - Acquisition UI page in SvelteKit (queue management, add items, process manually, filter by status, retry failed)
  - Background worker UI controls (start/stop, status indicator, check status)
  - Settings page diagnostics panel (health status, component checks, statistics, worker controls)
  - UTF-8 BOM handling in .env parser
  - Base64 auth helper for provider probes
  - All acquisition functions restored via Python subprocess delegation
  - Complete UI integration into Settings and Acquisition pages

## Next Up

1. Test end-to-end acquisition flow (add → process → download → scan)
2. System diagnostics command (doctor/status in Rust)
3. `npm run tauri build` release bundle with NSIS installer
5. AcoustID: install Chromaprint CLI (`fpcalc`) and validate fingerprint round-trip
6. Blank-machine validation on clean Windows VM
7. 4-hour audio soak

## Deferred But Explicit

- Arc sequencing (track journey builder)
- Agent/Architect (LLM-powered workflows)
- Chroma/vector migration to Rust
- Python enrich-cache migration
- Full oracle/recommendation parity
- Installer/release hardening once runtime stabilizes

