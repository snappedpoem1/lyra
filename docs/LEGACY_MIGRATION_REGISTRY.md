# Legacy Migration Registry

Last updated: March 8, 2026

## Purpose

This file is the authoritative cross-reference between legacy Python capabilities and their Rust migration targets.
It is the **build-to list** for every intelligence, enrichment, acquisition, and player feature that existed in the Python oracle and must be restored inside `crates/lyra-core`.

Read this alongside `docs/ROADMAP_ENGINE_TO_ENTITY.md` (milestone sequence) and `docs/MISSING_FEATURES_REGISTRY.md` (active gaps) — this file governs the *what*, the roadmap governs the *when*, and the gap registry governs the *delta*.

## Environment Note

All service credentials are live in the local `.env` file.
MusicBrainz, AcoustID, Discogs, Last.fm, Genius, ListenBrainz, Spotify, Real-Debrid, Qobuz, SoulSeek, and any other provider keys are already present and must be carried forward into Rust-owned provider config records rather than re-keyed.
Do not treat API access as a future prerequisite — the environment is ready.

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Landed in Rust runtime |
| 🔶 | Partially ported — structure exists, full parity not yet reached |
| ⬜ | Not yet started in Rust |
| 🚫 | Intentionally deferred — no active wave |

---

## Migration Table

| Legacy capability | Primary Python source(s) | Rust migration target | Wave | Status |
|---|---|---|---|---|
| Flask app bootstrap and runtime wiring | `oracle/api/app.py`, `oracle/runtime_services.py` | `lyra-core::state`, `::config`, Tauri app bootstrap | A | ✅ |
| Blueprint / API manifest | `oracle/api/registry.py` | `lyra-core::commands` + Tauri invoke/event registry | A | ✅ |
| Runtime / data-root authority | `oracle/config.py`, `oracle/data_root_migration.py` | `lyra-core::config` | A | ✅ |
| DB schema and migrations | `oracle/db/schema.py` | `lyra-core::db` | A | ✅ |
| Player service and queue-backed playback | `oracle/player/service.py`, `oracle/player/repository.py`, `oracle/player/audio_engine.py` | `lyra-core::playback`, `::queue` | A | ✅ |
| Player event bus | `oracle/player/events.py` | `lyra-core::playback` emitting Tauri events | A | ✅ |
| Library scan / import / index | `oracle/scanner.py`, `oracle/indexer.py`, `oracle/api/blueprints/library.py` | `lyra-core::library` | A | ✅ |
| Search | `oracle/search.py`, `oracle/api/blueprints/search.py` | `lyra-core::library`, `::commands` | A | 🔶 title/artist/album only; no FTS or CLAP-semantic search yet |
| Saved playlists CRUD and detail | `oracle/api/blueprints/playlists.py`, `docs/specs/SPEC-001_PLAYLIST_SCHEMA.md`, `docs/specs/SPEC-002_PLAYLIST_LOGIC.md` | `lyra-core::playlists` | A | ✅ |
| Vibe generation / save / list / materialize | `oracle/vibes.py`, `oracle/api/blueprints/vibes.py` | `lyra-core::playlists` | A | 🔶 vibe playlists imported from legacy DB; generation logic not yet ported |
| Duplicates detection | `oracle/duplicates.py` | `lyra-core::library` | A | ⬜ |
| Dimensional mood interpretation | `oracle/mood_interpreter.py` | `lyra-core::enrichment` or `::oracle` | B | ⬜ |
| Playlist intelligence and oracle playlist actions | `oracle/playlust.py`, `oracle/api/blueprints/oracle_actions.py` | `lyra-core::oracle`, `::playlists` | B | ⬜ |
| Brokered recommendations | `oracle/recommendation_broker.py`, `oracle/api/blueprints/recommendations.py` | `lyra-core::oracle` | B | ⬜ |
| Provider contract and evidence payloads | `oracle/provider_contract.py`, `docs/specs/SPEC-004_RECOMMENDATION_PROVIDER_CONTRACT.md` | `lyra-core::providers` | B | 🔶 provider config records exist; evidence payloads not yet structured |
| Provider health and watchlist | `oracle/provider_health.py`, `docs/specs/SPEC-006_PROVIDER_HEALTH_AND_WATCHLIST.md` | `lyra-core::providers`, `::logging` | B | ⬜ |
| Explainability surfaces | `oracle/explain.py`, `oracle/explainability.py`, `docs/specs/SPEC-005_UI_PROVENANCE_AND_DEGRADED_STATES.md` | `lyra-core::oracle` | B | ⬜ |
| Acquisition queue manager | `oracle/acquisition.py`, `oracle/api/blueprints/acquire.py` | `lyra-core::acquisition` | C | ✅ |
| 5-tier acquisition waterfall | `oracle/acquirers/waterfall.py`, `oracle/acquirers/__init__.py` | `lyra-core::acquisition` provider adapters | C | ⬜ |
| Acquisition guard / validator / prioritizer | `oracle/acquirers/guard.py`, `oracle/acquirers/validator.py`, `oracle/acquirers/taste_prioritizer.py` | `lyra-core::acquisition`, `::enrichment` | C | ⬜ |
| Ingest watcher and normalization lifecycle | `oracle/ingest_watcher.py`, `oracle/ingest_confidence.py`, `docs/specs/SPEC-007_INGEST_CONFIDENCE.md` | `lyra-core::library` | C | ⬜ |
| Diagnostics, doctor, status | `oracle/doctor.py`, `oracle/status.py`, `oracle/audit.py` | `lyra-core::logging`, `::commands` | C | ⬜ |
| CLI ops and maintenance commands | `oracle/cli.py` | split into `::commands`, import utilities, admin-only docs | C | 🔶 legacy import command exists; full CLI parity not yet ported |
| 10-dimension emotional scoring | `oracle/scorer.py` | `lyra-core::enrichment` | D | 🔶 DB tables + import from legacy DB done; live scorer not yet ported |
| Unified metadata enrichment | `oracle/enrichers/unified.py`, `oracle/api/blueprints/enrich.py` | `lyra-core::enrichment` | D | 🔶 enrich cache table exists; live enricher dispatch not yet ported |
| MusicBrainz enricher | `oracle/enrichers/musicbrainz.py` | `lyra-core::providers`, `::enrichment` | D | ⬜ keys available in `.env` |
| AcoustID enricher | `oracle/enrichers/acoustid.py` | `lyra-core::providers`, `::enrichment` | D | ⬜ keys available in `.env` |
| Discogs enricher | `oracle/enrichers/discogs.py` | `lyra-core::providers`, `::enrichment` | D | ⬜ keys available in `.env` |
| Last.fm enricher | `oracle/enrichers/lastfm.py` | `lyra-core::providers`, `::enrichment` | D | ⬜ keys available in `.env` |
| Genius enricher | `oracle/enrichers/genius.py` | `lyra-core::providers`, `::enrichment` | D | ⬜ keys available in `.env` |
| MBID identity spine | `oracle/enrichers/mb_identity.py`, `docs/specs/SPEC-010_MBID_IDENTITY_SPINE.md` | `lyra-core::enrichment` | D | ⬜ |
| Credit mapper | `oracle/enrichers/credit_mapper.py` | `lyra-core::enrichment` | D | ⬜ |
| Embeddings and vector store | `oracle/embedders/clap_embedder.py`, `oracle/chroma_store.py` | `lyra-core::enrichment` or separate vector crate | D | 🚫 Chroma migration deferred pending CLAP/DirectML Rust binding strategy |
| Artist biographer and shrine | `oracle/enrichers/biographer.py`, `oracle/api/blueprints/intelligence.py` | `lyra-core::library`, `::oracle` | D | ⬜ |
| Graph builder / constellation | `oracle/graph_builder.py`, `oracle/api/blueprints/discovery.py` | `lyra-core::oracle` | D | ⬜ |
| Scout and community weather | `oracle/scout.py`, `oracle/integrations/listenbrainz.py`, `docs/specs/SPEC-008_SCOUT_COMMUNITY_WEATHER.md` | `lyra-core::oracle`, `::providers` | D | ⬜ keys available in `.env` |
| Radio / deep-cut / hunt surfaces | `oracle/radio.py`, `oracle/deepcut.py`, `oracle/hunter.py` | `lyra-core::oracle` | D | ⬜ |
| Taste seeding and taste backfill | `oracle/taste.py`, `oracle/taste_backfill.py` | `lyra-core::oracle` | D | 🔶 taste_profile table + legacy import exist; live backfill engine not yet ported |
| Companion pulse event system | `oracle/companion/pulse.py`, `oracle/api/blueprints/companion.py`, `docs/specs/SPEC-011_COMPANION_PULSE.md` | `lyra-core::native`, `::oracle`, Tauri events | E | ⬜ |

---

## Wave Summary

Each wave is a focused delivery scope. Waves are sequential in intent but segments within a wave can be parallelized.

### Wave A — Player core, library, session, playlists

**Goal:** Everything needed for a working local player that replaces legacy playback end-to-end.

| # | Capability | Rust target | Notes |
|---|---|---|---|
| A-1 | Flask bootstrap / runtime wiring | `lyra-core::state`, `::config`, Tauri setup | ✅ landed |
| A-2 | DB schema and migrations | `lyra-core::db` | ✅ landed |
| A-3 | Player service, queue-backed playback, event bus | `lyra-core::playback`, `::queue` | ✅ landed |
| A-4 | Library scan / import / index | `lyra-core::library` | ✅ landed |
| A-5 | Saved playlists CRUD | `lyra-core::playlists` | ✅ landed |
| A-6 | Vibe playlists (import path) | `lyra-core::playlists` | 🔶 import only |
| A-7 | Basic search | `lyra-core::library` | 🔶 string match only |
| A-8 | Duplicates detection | `lyra-core::library` | ⬜ pending |

---

### Wave B — Recommendations, provider contracts, explainability

**Goal:** Broker recommendations using live provider keys. Surface provenance and degraded states in the UI.

| # | Capability | Rust target | Notes |
|---|---|---|---|
| B-1 | Provider contract and evidence payloads | `lyra-core::providers` | needs `ProviderEvidence` struct and contract trait |
| B-2 | Provider health and watchlist | `lyra-core::providers`, `::logging` | circuit-breaker pattern per `SPEC-006` |
| B-3 | Brokered recommendations | `lyra-core::oracle` | depends on B-1 and B-2 |
| B-4 | Mood interpreter | `lyra-core::enrichment` | dimensional label → playlist seed |
| B-5 | Playlist intelligence / oracle actions | `lyra-core::oracle`, `::playlists` | depends on B-3 |
| B-6 | Explainability surfaces | `lyra-core::oracle` | per `SPEC-005`; why-did-I-get-this provenance chain |

---

### Wave C — Acquisition, ingest, diagnostics

**Goal:** Queue-driven acquisition using live Qobuz/Slskd/Real-Debrid/SpotDL keys. Normalize and verify ingest. Surface runtime health.

| # | Capability | Rust target | Notes |
|---|---|---|---|
| C-1 | Acquisition queue manager | `lyra-core::acquisition` | ✅ DB + basic queue already landed |
| C-2 | 5-tier acquisition waterfall | `lyra-core::acquisition` provider adapters | Qobuz/Streamrip/Slskd/RealDebrid/SpotDL adapters |
| C-3 | Guard / validator / taste-prioritizer | `lyra-core::acquisition`, `::enrichment` | prioritization uses taste_profile scores |
| C-4 | Ingest watcher and confidence | `lyra-core::library` | file-system watcher + confidence scoring per `SPEC-007` |
| C-5 | Diagnostics, doctor, status | `lyra-core::logging`, `::commands` | health endpoints and CLI-equivalent Tauri commands |
| C-6 | CLI ops | `::commands` + admin utilities | import triggers, manual queue ops |

---

### Wave D — Enrichment, MBID, intelligence, graph, scout

**Goal:** Port all metadata enrichment pipelines, build the MBID identity spine, and restore the graph and community discovery surfaces. All enricher keys are live.

| # | Capability | Rust target | Notes |
|---|---|---|---|
| D-1 | 10-dimension scorer | `lyra-core::enrichment` | per-track score computation; DB table already landed |
| D-2 | Unified metadata enricher | `lyra-core::enrichment` | dispatcher: MB → AcoustID → Discogs → Last.fm → Genius priority chain |
| D-3 | MusicBrainz enricher | `lyra-core::providers`, `::enrichment` | key in `.env` |
| D-4 | AcoustID enricher | `lyra-core::providers`, `::enrichment` | key in `.env` |
| D-5 | Discogs enricher | `lyra-core::providers`, `::enrichment` | key in `.env` |
| D-6 | Last.fm enricher | `lyra-core::providers`, `::enrichment` | key in `.env` |
| D-7 | Genius enricher | `lyra-core::providers`, `::enrichment` | key in `.env` |
| D-8 | MBID identity spine | `lyra-core::enrichment` | per `SPEC-010`; artist_mbid + recording_mbid columns already in schema |
| D-9 | Credit mapper | `lyra-core::enrichment` | producer/songwriter/featured-artist credits |
| D-10 | Artist biographer / shrine | `lyra-core::library`, `::oracle` | artist bio + top-tracks surface |
| D-11 | Graph builder / constellation | `lyra-core::oracle` | sonic neighbor graph; feeds Discover |
| D-12 | Scout / community weather | `lyra-core::oracle`, `::providers` | ListenBrainz key in `.env` |
| D-13 | Radio / deep-cut / hunt | `lyra-core::oracle` | session queuing algorithms |
| D-14 | Taste backfill | `lyra-core::oracle` | history-driven taste dimension inference |
| D-15 | Embeddings and vector store | deferred — separate strategy needed | Chroma + CLAP/DirectML binding; see note below |

> **D-15 note:** The existing `chroma_storage/` directory and 2,454 CLAP embeddings are preserved. The Rust port requires either: (a) a Rust CLAP inference binding via ort/DirectML, or (b) a kept-isolated Python micro-service that is not part of player startup. Decision is deferred until Wave D otherwise stabilizes.

---

### Wave E — Companion pulse, native ritual, secondary intelligence

**Goal:** Real-time contextual awareness surface. Tauri native hooks as the event substrate.

| # | Capability | Rust target | Notes |
|---|---|---|---|
| E-1 | Companion pulse event system | `lyra-core::native`, `::oracle`, Tauri events | per `SPEC-011`; heartbeat + context emission |

---

## Specs Index

Reference these when implementing the corresponding capability:

| Spec | Title | Relevant Wave |
|---|---|---|
| `docs/specs/SPEC-001_PLAYLIST_SCHEMA.md` | Playlist schema | A |
| `docs/specs/SPEC-002_PLAYLIST_LOGIC.md` | Playlist logic | A |
| `docs/specs/SPEC-004_RECOMMENDATION_PROVIDER_CONTRACT.md` | Provider contract | B |
| `docs/specs/SPEC-005_UI_PROVENANCE_AND_DEGRADED_STATES.md` | Explainability / degraded states | B |
| `docs/specs/SPEC-006_PROVIDER_HEALTH_AND_WATCHLIST.md` | Provider health | B |
| `docs/specs/SPEC-007_INGEST_CONFIDENCE.md` | Ingest confidence | C |
| `docs/specs/SPEC-008_SCOUT_COMMUNITY_WEATHER.md` | Scout / community weather | D |
| `docs/specs/SPEC-010_MBID_IDENTITY_SPINE.md` | MBID identity spine | D |
| `docs/specs/SPEC-011_COMPANION_PULSE.md` | Companion pulse | E |

---

## Update Protocol

When a capability moves from ⬜ → 🔶 → ✅:

1. Update the status symbol in the migration table above.
2. Update `docs/MISSING_FEATURES_REGISTRY.md` if it references the same gap.
3. Update `docs/ROADMAP_ENGINE_TO_ENTITY.md` wave section if the milestone changes.
4. Record the session in `docs/SESSION_INDEX.md`.
