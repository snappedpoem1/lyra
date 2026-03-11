# Session Log - S-20260310-08

**Date:** 2026-03-10
**Goal:** Backend-only Phase 1 audit, backend autonomy verification, audio data hygiene hardening, recommendation engine validation
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

The canonical Rust backend already owned playback, queue, library, provider config, and the recommendation broker, but Phase 1 backend integrity was uneven in three places:

- schema/runtime drift existed around `tracks.status`, `tracks.version_type`, `tracks.confidence`, and a stale `artist_connections` query path
- provider-fed metadata had no strict canonical catalog table, so normalization and junk rejection were not enforced at the DB boundary
- provider HTTP behavior was fragmented, with no shared retry/backoff/cache layer and no backend-owned Spotify OAuth session model

---

## Work Done

- [x] Audited `lyra-core` against the backend mandate and fixed real schema/runtime mismatches instead of papering over them
- [x] Added canonical provider-track normalization in `crates/lyra-core/src/audio_data.rs` with rejection of karaoke, tribute, cover, lo-fi remix, nightcore, slowed, and sped-up variants
- [x] Added strict provider catalog persistence and OAuth session tables in SQLite, plus backfill migrations for `tracks.status`, `tracks.version_type`, and `tracks.confidence`
- [x] Hardened provider transport with cache reuse, exponential backoff, and 429/5xx retry handling through `crates/lyra-core/src/provider_runtime.rs`
- [x] Wired library ingest, enrichment, acquisition import, and ListenBrainz weather recommendations into the canonical normalization/persistence path
- [x] Added backend-owned Spotify OAuth session persistence and refresh support, with validation aware of refreshable user sessions instead of only client-credential probes
- [x] Replaced the broken recommendation graph query against `artist_connections` with the canonical `connections` table
- [x] Verified backend-only autonomy with cargo checks and full `lyra-core` tests, including cached weather, live-fallback weather, and non-library acquisition-lead tests

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | `local changes only (no commit yet)` |

---

## Key Files Changed

- `crates/lyra-core/src/audio_data.rs` - canonical provider-track normalization and strict provider-catalog persistence
- `crates/lyra-core/src/provider_runtime.rs` - shared cache/retry/backoff transport for external provider JSON calls
- `crates/lyra-core/src/db.rs` - schema hardening for track state/version/confidence, strict provider catalog table, and provider OAuth session table
- `crates/lyra-core/src/providers.rs` - backend-owned Spotify OAuth session persistence, refresh, and validation integration
- `crates/lyra-core/src/oracle.rs` - fixed canonical graph query path and normalized/persisted weather-lane recommendation handling
- `crates/lyra-core/src/library.rs` - ingest-time classification persisted as track status/version/confidence with quarantine support
- `crates/lyra-core/src/enrichment.rs` - provider fetches now run through shared cache/retry transport and persist normalized provider payloads
- `crates/lyra-core/src/acquisition.rs` - Spotify library import now normalizes/filter-rejects provider data before queueing and stores canonical provider evidence
- `docs/PROJECT_STATE.md` - updated backend autonomy, data hygiene, and remaining-gap truth

---

## Result

Yes. The backend now enforces a canonical provider-track schema, rejects obvious non-canonical junk variants before they contaminate queue/recommendation flows, persists normalized external evidence, retries and throttles external provider traffic defensively, and owns Spotify session refresh metadata without needing a frontend trigger. The recommendation engine also proved it can emit adjacent, non-library acquisition leads entirely from backend logic.

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `cargo check -p lyra-core` and `cargo test -p lyra-core`

---

## Next Action

Expose a canonical backend Spotify authorization-code exchange entrypoint, then push direct audio-feature-guided vibe matching deeper into composer/discovery scoring using `spotify_features` plus the new normalized provider catalog.
