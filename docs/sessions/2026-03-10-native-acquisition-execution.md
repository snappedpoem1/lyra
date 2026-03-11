# S-20260310-13: Native Acquisition Execution + Downloader Waterfall + Official Variant Validator

**Date**: 2026-03-10
**Goal**: Execute the native acquisition waterfall end-to-end, wire yt-dlp as final fallback, build official-release backup validator, and physically repopulate `A:\Music`.

## What Changed

### Official Variant Backup Validator (3 layers)

1. **catalog.rs** — `should_skip_release_group` split into hard-skip types (compilation, dj-mix, remix, soundtrack, spokenword) vs variant types (live, demo). Official variants like HAARP or "3 Demos, Reworked" pass through; bootleg event titles are still blocked.

2. **acquisition_planning.rs** — `is_official_variant_album` check bypasses variant-sensitive junk needles (soundcheck, instrumental version, demo version, acoustic) when the album title matches official patterns (live at/from/in, deluxe, special edition, remastered, unplugged, haarp, demos reworked, live edition).

3. **audio_data.rs** — `should_reject_variant` allows Remix/Live/Special `VersionType` through when `is_official_variant_album(album)` returns true. Junk and Cover types are always blocked.

### Downloader Waterfall

- **acquisition_dispatcher.rs** — Added `try_native_ytdlp` function wiring `YtdlpTier` into the waterfall chain as final fallback: T1 Qobuz → T2 Streamrip → T3 Slskd → T5 SpotDL → T4 yt-dlp.
- **waterfall.rs** — Made `find_binary` public on `YtdlpTier`.
- **lib.rs** — Added yt-dlp to preflight `downloader_tools` array.
- **commands.rs** — Added `Default` derive to `AcquisitionQueueItem`.

### Validator Fix

- **validator.rs** — `validate_track_text` now checks junk patterns on raw inputs BEFORE `clean_title` strips markers like `[soundcheck]`.

### New Binary

- **bin/acquisition_runner.rs** — CLI for processing acquisition queue items with `--limit N` and `--dry-run` flags.

## Test Results

- 7 catalog backup validator tests (HAARP, bootleg, compilation, remix, demo EP, title-only live)
- 4 acquisition_planning official variant bypass tests
- 2 validator junk-guard tests (lofi, soundcheck)
- All `cargo test -p lyra-core --lib` passing

## Queue Execution Results

- **Preflight**: ready=true, downloader_available=true, disk_ok=true, library_root_ok=true
- **Providers on PATH**: spotdl, streamrip (rip), yt-dlp
- **Processed**: 18 items, 18 success, 0 failed
- **Provider used**: SpotDL (T5) — Qobuz service and Slskd containers not running
- **Files landed in A:\Music**: 13 files across 3 albums (5 FLAC, 8 MP3)
  - Coheed and Cambria/Coheed and Cambria EP (5 tracks)
  - Coheed and Cambria/Demos (3 tracks)
  - Coheed and Cambria/The Second Stage Turbine Blade (5 tracks, 4 FLAC + 1 MP3 dedup)
- **Queue remaining**: 811 queued items

## Files Changed

| File | Change |
|------|--------|
| `crates/lyra-core/src/catalog.rs` | Split hard-skip vs variant types, added bootleg heuristics, 7 tests |
| `crates/lyra-core/src/acquisition_dispatcher.rs` | Added `try_native_ytdlp`, wired into waterfall chain |
| `crates/lyra-core/src/acquisition_planning.rs` | Official variant bypass for variant-sensitive junk, 4 tests |
| `crates/lyra-core/src/audio_data.rs` | `should_reject_variant` allows official variants, `is_official_variant_album` |
| `crates/lyra-core/src/validator.rs` | Raw-input junk check before clean_title |
| `crates/lyra-core/src/waterfall.rs` | `find_binary` made public on YtdlpTier |
| `crates/lyra-core/src/lib.rs` | yt-dlp added to preflight downloader_tools |
| `crates/lyra-core/src/commands.rs` | `Default` derive on AcquisitionQueueItem |
| `crates/lyra-core/src/bin/acquisition_runner.rs` | NEW: CLI queue processor |

## Still Open

- Qobuz service container (T1 lossless) not running — SpotDL (T5 lossy) served as primary
- Slskd container (T3 FLAC) not running
- 811 queued items remaining
- Brand New and Muse tracks not yet in queue (only Coheed queued via discography_probe)

## Next Best Wave

- Start Qobuz and Slskd Docker containers for lossless-first acquisition
- Queue Brand New and Muse discographies via discography_probe
- Continue draining the remaining 811 queued items
- Run MB artist intelligence ingestion across populated library
- Run audio feature batch extraction across populated library
