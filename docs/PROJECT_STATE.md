# Lyra Project State

Last audited: March 8, 2026

## Canonical Runtime Truth

Lyra's canonical runtime is:

- Tauri 2 desktop shell
- SvelteKit SPA renderer
- Rust application core in `crates/lyra-core`
- Rust-owned SQLite local store

Python is not part of canonical startup, playback, queue, library, or normal app operation.
Legacy Python and oracle surfaces remain in-repo as migration-source logic, not as the active runtime.

## Product Reality

Lyra's native foundation is real.
The remaining challenge is product identity depth, not whether a desktop shell can launch.

Implemented now:

- Python-free desktop boot path
- direct Tauri invoke path into Rust
- Rust-owned SQLite init, migrations, and session state
- library roots, scan/import, playlists, queue, settings, and playback
- Windows SMTC and audio device selection
- provider config records, validation hooks, env import, and secret storage paths
- canonical app shell with collapsible left and right rails, persistent mini player, and persistent Lyra composer line
- acquisition workflow with persisted lifecycle state, queue ordering, cancellation, preflight checks, backend event streaming, downstream organize/scan/index follow-through, and shell-integrated diagnostics
- Horizon release intelligence subsystem (Prowlarr as indexer-health and release discovery authority, decoupled from T4 acquisition execution)
- partial artist, enrichment, recommendation, and taste surfaces, including shell-visible provenance, MBID identity summaries, and connected discovery/playlist evidence hooks

Partial or scaffolded:

- explainability coverage across the product
- enrichment provenance and confidence visibility across the full product, especially for saved playlists, deep recommendation flows, and broader explanation coverage
- playlist authorship and narrative generation
- graph and constellation discovery depth
- visible taste tooling and dimensional steering
- curation workflows with rollback and undo
- packaged desktop release confidence
- final acquisition trust hardening around external metadata validation parity and full removal of the transitional Python waterfall executor

## Implemented Now

The canonical app already behaves like a credible native local player and library tool:

- native playback and session behavior
- local library scan/import
- playlists, queue, settings, and now-playing surfaces
- one connected oracle shell with shared context, provenance, bridge, queue, and acquisition rails
- provider plumbing and secure secret handling
- acquisition workflow with event-backed lifecycle authority, detailed failure semantics, queue reordering/cancellation, and completion only after organize/scan/index follow-through
- acquisition execution no longer hard-blocked on `.venv` Python when native `qobuz` service, `streamrip`, `slskd`, or `spotdl` providers are available; Python remains only for the remaining legacy waterfall fallback paths
- Prowlarr decoupled from acquisition execution: Prowlarr is now horizon intelligence (release discovery, upcoming releases, indexer health) via `oracle/horizon/prowlarr_releases.py` and `/api/horizon/*`; T4 torrent tier now routes through `oracle/acquirers/magnet_sources.py` to `realdebrid.acquire_from_magnets()` without a Prowlarr gate
- Horizon workspace surface added to the frontend at `/routes/horizon/` for release intelligence and indexer health
- track-level and artist-level provenance summaries with MBID-first identity surfaces
- discovery and generated-playlist surfaces that can publish provenance and reason context into the shared shell
- early recommendation, artist, taste, and enrichment surfaces

## Still Missing

Lyra still undersells its intended identity in the canonical runtime.
The biggest missing pieces are:

- explainable recommendation that is visible, durable, and broad
- playlist-first authored journeys with reason payloads
- bridge-track and related-artist discovery depth
- provenance-aware enrichment with confidence visibility
- visible, steerable taste and dimensional signals
- deeper trust semantics for transitional acquisition execution, especially external metadata-validation parity and eventual Python-bridge reduction

## Legacy Migration Source Reality

Useful product logic still exists in Python.
That code must be inspected before recreating missing canonical features.

High-value legacy logic includes:

- acquisition waterfall, prioritization, guard, validator, and ingest confidence
- recommendation broker and explainability flows
- playlist and vibe generation behavior
- taste updates and backfill
- graph builder and scout discovery logic
- unified enrichment, MBID identity, credits, and biography
- duplicate handling, curation workflows, and worker sequencing

Obsolete runtime scaffolding also exists there.
Agents must separate scaffolding from durable product behavior before porting.

## Legacy-to-Canonical Port Rule

Before implementing a missing canonical feature:

1. Inspect the relevant legacy Python and oracle-era logic first.
2. Recover the solved workflow, state machine, retry behavior, payload shape, or ranking semantics.
3. Port that behavior deliberately into Rust, Tauri, and Svelte.
4. Do not recreate solved logic from memory.
5. Do not bring back the legacy runtime architecture.
6. Record the legacy-to-canonical mapping in docs or the session log.

## Current Priority Order

The active execution order is:

1. `G-060` Acquisition workflow parity
2. `G-061` Enrichment provenance and confidence
3. `G-063` Playlist intelligence parity
4. `G-064` Discovery graph depth
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

This ordering is deliberate:

- workflow visibility and trust first
- provenance and identity confidence second
- playlist and oracle intelligence third
- graph and bridge discovery fourth
- curation safety fifth
- packaging and soak last as a release gate

## Configuration And Credential Reality

Provider and API configuration already exists in the repo and local environment.
This is not a greenfield configuration problem.

Grounded facts:

- Python loads `.env` from established config modules
- Rust imports `.env` data through `crates/lyra-core/src/providers.rs`
- Rust persists provider config records in SQLite
- Rust already maintains provider capability metadata and validation flows
- Rust already supports OS keyring storage and retrieval for provider secrets

Do not expose secret values in docs, logs, or summaries.
