# Lyra Project State

Last audited: March 8, 2026

## Runtime Truth

- Canonical runtime is:
  - Tauri 2 desktop shell
  - SvelteKit SPA renderer
  - Rust application core in `crates/lyra-core`
  - Rust-owned SQLite local store
- Python is not part of canonical startup, playback, queue, library, or normal app operation.
- Legacy Python/oracle surfaces remain in-repo as migration-source logic and reference material.

## Honest Product State

Lyra's native foundation is ahead of its user-facing product identity layer.

What is strong already:

- native playback and session behavior
- local library scan/import
- playlists, queue, settings, and now-playing surfaces
- provider config records, env import, validation hooks, and secret storage paths
- acquisition baseline and diagnostics
- early recommendation, artist, taste, and enrichment surfaces

What is still incomplete:

- explainability is partial and not yet pervasive
- playlist authorship and narrative generation are not yet a first-class canonical experience
- graph and constellation discovery are still thin relative to intended product shape
- provenance and confidence visibility are inconsistent
- dimensional and emotional scoring exists only in partial or non-portable form
- the canonical UI/runtime still undersells Lyra as an intelligence and curation system

## Landed Native Foundation

Implemented in the Rust/Tauri/Svelte runtime:

- Python-free Tauri boot path
- direct Rust command bridge
- Rust-owned SQLite init and migrations
- library roots persistence
- file scan/import with lofty metadata extraction
- playlist CRUD and queue persistence
- settings persistence
- provider config records and capability registry
- legacy `.env` and legacy DB import path
- native playback, seek, repeat/shuffle, and session restore
- SMTC integration on Windows
- audio device selection
- enrichment adapter baseline in Rust
- recommendation and taste-profile baseline surfaces
- artist profile route and acquisition queue UI

## Product-Identity Gap

The repo is no longer blocked on "can Lyra be a native local desktop app."
That baseline exists.

The main remaining gap is whether the canonical product actually delivers its differentiator:

- explainable recommendation
- authored playlist journeys
- visible taste tooling
- bridge and related-artist discovery
- provenance-aware enrichment
- graph-driven exploration

Those capabilities are only partially present today.
Some are early Rust ports.
Some still live mainly in Python implementation surfaces.
Some are missing from the canonical UI even when lower-level logic exists.

## Python Migration-Source Reality

Valuable implemented logic still exists in Python and should be treated as migration source, not discarded noise.

Important Python areas with meaningful logic include:

- acquisition waterfall and prioritization
- recommendation broker and explainability
- vibe/playlist generation and reason enrichment
- taste profile updates and backfill
- graph builder and scout discovery
- unified enrichment flows, MBID identity, credits, and artist biography
- duplicate handling, curation workflows, and ingest lifecycle logic
- worker/process sequencing around graph, taste, enrichment, and acquisition maintenance

Obsolete runtime scaffolding also exists there, but agents should distinguish scaffolding from business logic before replacing anything.

## Configuration And Credential Reality

Provider/API configuration already exists in the repo and local environment.
This is not a greenfield configuration problem.

Grounded facts in the current codebase:

- Python loads `.env` from repo-root-oriented config modules such as `oracle/config.py`, `oracle/api/app.py`, and other integration entry points
- Rust imports `.env` data through `crates/lyra-core/src/providers.rs`
- Rust persists provider config records in SQLite `provider_configs`
- Rust already maintains provider capability metadata and validation flows
- Rust already supports OS keyring storage and retrieval for provider secrets

Do not expose secret values in docs, logs, or summaries.

## Current Execution Truth

The most important next work is not "more generic player correctness."
The most important next work is porting and surfacing Lyra's actual intelligence and curation identity while keeping the native runtime stable.

That means:

- port real Python process logic where it already exists
- surface reasons, provenance, confidence, and taste signals in the canonical UI
- prioritize playlist intelligence and discovery depth earlier in the roadmap
- keep release/stability work honest and bounded instead of letting it erase product intent
