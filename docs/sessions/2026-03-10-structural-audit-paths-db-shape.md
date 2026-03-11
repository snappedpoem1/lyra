# Session Log - S-20260310-07

**Date:** 2026-03-10
**Goal:** Audit repo structure for oversized files, legacy path leakage, and old DB shape usage; then execute migration-first canonical Spotify data cutover
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

Structural audit found a high-risk split between canonical runtime DB usage and legacy-attached Spotify reads.
Taste seeding, Spotify pressure, and acquisition queue seeding could read different sources depending on path.

---

## Work Done

- [x] Added canonical Spotify tables to Rust-owned schema: `spotify_history`, `spotify_library`, `spotify_features`.
- [x] Added migration helper in `LyraCore` to import Spotify history/library/features from legacy DB into canonical DB.
- [x] Ran startup migration attempt in `LyraCore::new` when legacy DB is present.
- [x] Rewired Spotify pressure in composer intelligence to read canonical tables directly (removed legacy attach path for this flow).
- [x] Rewired Spotify gap summary to canonical tables (now reports canonical DB path).
- [x] Added explicit Spotify migration provenance diagnostics in `SpotifyGapSummary` (`sourceMode`, `legacyImportObserved`, `lastLegacyImportAt`, and last imported row counts).
- [x] Rewired Spotify acquisition seed to import from canonical `spotify_library`, with ownership checks against normalized canonical track schema.
- [x] Updated affected intelligence test to seed canonical Spotify context directly.
- [x] Removed remaining legacy-default assumptions:
  - legacy DB discovery is now explicit via `LYRA_DB_PATH` (no implicit repo-root `lyra_registry.db` fallback in runtime import/seed path selection).
  - `taste_backfill` runner now resolves canonical DB (`LYRA_DB_PATH` → `LYRA_DATA_ROOT\\db\\lyra.db` → `%LOCALAPPDATA%\\Lyra\\dev\\db\\lyra.db` → `%APPDATA%\\com.lyra.player\\db\\lyra.db`).
- [x] Smoke validated with `cargo check -p lyra-core` and full `cargo test -p lyra-core` (45 passing).

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | local changes (no commit yet) |

---

## Key Files Changed

- `crates/lyra-core/src/db.rs` - canonical Spotify table/index definitions added.
- `crates/lyra-core/src/lib.rs` - legacy→canonical Spotify migration helper + startup migration + canonical gap/seed usage.
- `crates/lyra-core/src/intelligence.rs` - Spotify pressure now canonical-table driven.
- `crates/lyra-core/src/acquisition.rs` - Spotify library queue import now source-agnostic and canonical ownership-aware.
- `docs/PROJECT_STATE.md` - runtime capability truth updated for canonical Spotify evidence ownership.
- `docs/SESSION_INDEX.md` - session ledger updated.

---

## Result

Canonical runtime no longer requires attached legacy Spotify tables for the active intelligence/gap/acquisition paths updated in this session.
Legacy DB now acts as migration input to populate canonical Spotify tables, reducing mixed-source drift risk.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `cargo check -p lyra-core`, `cargo test -p lyra-core`, `desktop/renderer-app npm run check`

---

## Next Action

Complete canonical cutover by removing remaining runtime fallback text/path assumptions (`lyra_registry.db` messaging and legacy-focused backfill bin path defaults), then add explicit migration-provenance diagnostics in shell surfaces.
