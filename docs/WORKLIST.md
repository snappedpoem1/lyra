# Worklist

Last updated: March 8, 2026

## Current State

- Rust/Tauri/SvelteKit is the active runtime path.
- Python/oracle runtime surfaces are preserved as legacy reference only.
- Wave 2 delivered: real rodio audio backend, lofty tag extraction, full playlist editing, position ticker with auto-advance.
- Wave C delivered: session restore on relaunch, stop-at-end persistence, Windows SMTC taskbar bridge.
- Wave D delivered: audio device enumeration/selection (cpal), settings UI device picker, live MusicBrainz adapter (ureq), `enrich_track` Tauri command.
- Wave E delivered: background enrichment on scan (up to 30 tracks post-scan), `enrich_library` command (50 tracks), library UI enrichment panel (MBID, release, match score).
- Wave F: full build/lint/test pass — `cargo clippy -D warnings` clean, `cargo build` clean, `npm run build` clean, app launches.
- Wave G: AcoustID fingerprint adapter — `fpcalc` shell-out + AcoustID API lookup replacing null stub; graceful not-available fallback when `fpcalc` absent.

## Next Up

1. AcoustID: install Chromaprint CLI on dev machine (`fpcalc`) and validate fingerprint round-trip against a known track
2. Begin Rust parity work for provider migration:
   - provider-specific credential storage (system keychain via keyring crate)
   - first real acquisition adapter port (Qobuz OAuth)
3. MPRIS integration (Linux — deferred; Windows SMTC is done)
4. Release hardening:
   - NSIS installer with correct dist layout
   - blank-machine validation on a clean Windows VM
   - code-signing stub

## Deferred But Explicit

- Chroma/vector migration
- Python enrich-cache migration
- acquisition history migration
- full oracle/recommendation parity
- installer/release hardening once runtime behavior stabilizes

