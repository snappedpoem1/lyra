# Lyra Gap Registry

Last audited: March 8, 2026

This file tracks active canonical product gaps only.

## Gap Framing

The most important open gaps are not generic player bugs.
They are the missing or incomplete differentiators that should make Lyra feel like a self-owned music intelligence and curation system.

Each gap below distinguishes between:

- implemented now in the canonical runtime
- partial or scaffolded in the canonical runtime
- available as legacy behavior but not yet ported

## Legacy-To-Canonical Rule

Before closing any gap below:

1. Inspect the relevant legacy Python or oracle logic first.
2. Recover the solved workflow, payload shape, retry logic, explanation semantics, or ranking behavior.
3. Port the useful behavior into Rust, Tauri, and Svelte.
4. Do not recreate solved logic from memory.
5. Do not restore legacy runtime architecture.

## Active Gap Matrix

| ID | Area | Status | Implemented Now | Missing Or Partial | Legacy Sources To Inspect Next |
| --- | --- | --- | --- | --- | --- |
| G-060 | Acquisition workflow parity | implemented with transitional risk | Canonical acquisition queue now persists lifecycle state, queue order, cancellation, timestamps, provider/tier/worker diagnostics, validation confidence, destination-root routing, output paths, downstream organize/scan/index flags, backend lifecycle events, and UI-visible retry/clear/reorder/cancel/preflight controls in Rust/Tauri/Svelte; native `qobuz` service, `streamrip`, `slskd`, and `spotdl` execution can run without `.venv` Python | Transitional waterfall execution still needs external metadata-validator parity and eventual reduction of Python-bridge dependence, but guard checks, duplicate detection, taste-based priority seeding, destination selection, stronger active cancellation, and removal of the hard Python gate now live in Rust | `oracle/acquirers/waterfall.py`, `oracle/acquisition.py`, `oracle/acquirers/smart_pipeline.py`, `oracle/acquirers/taste_prioritizer.py`, `oracle/acquirers/guard.py`, `oracle/acquirers/validator.py`, `oracle/ingest_watcher.py` |
| G-061 | Enrichment provenance and confidence | partial, active | Canonical enrichment adapters, cache, track-level provenance summaries, artist-level MBID-first identity summaries, shell-visible inspector provenance, and first-pass discovery and generated-playlist evidence hooks now exist | Provider provenance, confidence, and degraded-state honesty are still inconsistent across saved playlists and broader explanation flows, and more legacy evidence semantics still need to be ported | `oracle/enrichers/unified.py`, provider enrichers, `oracle/enrichers/mb_identity.py`, `oracle/explainability.py` |
| G-063 | Playlist intelligence parity | partial | Canonical playlists and queue flows are functional | Authored act and narrative generation, durable reason payloads, and first-class "why this track?" playlist behavior are still incomplete | `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, related blueprint flows |
| G-064 | Discovery graph depth | partial | Canonical artist and recommendation surfaces exist | Graph-backed exploration, bridge workflows, and constellation-style discovery remain thin | `oracle/graph_builder.py`, `oracle/scout.py`, `oracle/recommendation_broker.py` |
| G-062 | Curation workflows | partial | Canonical library and playlist basics exist | Duplicate resolution, cleanup preview/apply, rollback metadata, and stewardship UX are not yet fully restored | `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py`, `oracle/ingest_watcher.py` |
| G-065 | Packaged desktop confidence | partial | Canonical runtime builds and launches locally | Clean-machine installer proof, packaged runtime confidence, and soak validation remain open | packaged validation scripts, installed-layout runtime checks, parity soak artifacts |

## Integration And Config Reality

Feature work is not blocked by a blank configuration story.
The repo already has:

- repo-root `.env` loading on Python surfaces
- Rust `.env` import into `provider_configs`
- provider capability metadata in Rust
- provider validation hooks in Rust
- OS keyring support in Rust

Future agents should treat provider and config plumbing as existing infrastructure to reuse and normalize, not as a future prerequisite.

## Execution Order

1. `G-060` Acquisition workflow parity
2. `G-061` Enrichment provenance and confidence
3. `G-063` Playlist intelligence parity
4. `G-064` Discovery graph depth
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

Current execution note:
`G-060` now has live backend lifecycle authority, Rust-owned queue trust checks, destination routing, and library-complete completion semantics, so the next active implementation run should stay on `G-061` unless acquisition regressions are discovered.
