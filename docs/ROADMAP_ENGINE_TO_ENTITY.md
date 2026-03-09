# Lyra Roadmap

Last updated: March 8, 2026

## Mission Lock

Lyra is a desktop-first, playlist-first, local-first music intelligence and curation platform with native playback.

It is not just a native player rewrite.
The player, queue, library, and installer work exist to support the real product:

- explainable recommendation
- authored playlist journeys
- bridge-track and related-artist discovery
- visible taste and dimensional scoring
- provenance-aware enrichment
- graph and constellation exploration
- self-owned listening intelligence

Canonical runtime:

- Tauri 2 shell
- SvelteKit frontend
- Rust application core
- SQLite local store

Python is not canonical runtime.
Python is still a major migration source for solved process logic, provider integration behavior, and product intent that must be ported forward deliberately.

## Decision Lock

1. No Python in canonical startup, playback, queue, library, or settings flow.
2. No localhost backend dependency.
3. Rust owns runtime state, DB, library, queue, playback surface, provider configs, and native integration.
4. SvelteKit owns the active UI layer.
5. Future intelligence work must extend the Rust core instead of reviving sidecars.
6. Existing Python implementations should be mined for already-solved process flow before inventing replacement behavior.
7. Existing environment/config/provider setup already exists and should be integrated into the canonical architecture, not recreated from scratch.

## Current Milestone

The native foundation is real and increasingly usable:

- Rust/Tauri/Svelte now own the canonical runtime
- local playback, queue, playlists, scanning, settings, provider config records, and an event-backed acquisition workflow exist
- recommendation, artist, enrichment, and taste surfaces are partially present in the canonical app

The gap is product identity, not just runtime correctness.
Lyra still needs much stronger user-visible intelligence, explainability, authorship, and discovery depth before the product matches its intended shape.

## Forward Roadmap

### Wave 1 - Runtime Foundation And Provider Plumbing

Keep this stable, but treat it as foundation work:

- playback/session correctness
- scan/import reliability
- provider config records
- credential import and safe storage
- acquisition lifecycle authority, queue trust, and post-acquisition library follow-through

### Wave 2 - Explainability And Provenance Surfaces

Bring the intelligence layer into view early:

- recommendation reasons that users can inspect
- provider/source provenance in recommendation and enrichment flows
- confidence visibility and degraded-state honesty
- MBID-first identity surfaces where available

### Wave 3 - Playlist Intelligence And Authorship

Move playlist identity forward instead of treating it as a late garnish:

- act and narrative playlist generation
- persisted per-track reason payloads
- "Why is this track here?" surfaces
- save/apply flows that preserve authored structure

### Wave 4 - Discovery Graph And Bridge Exploration

Restore discovery depth as a first-class differentiator:

- related-artist graph actions
- bridge-track and bridge-artist workflows
- constellation-style exploration
- taste-aware discovery session memory

### Wave 5 - Visible Taste And Dimensional Scoring

Make the internal scoring layer legible and useful:

- emotional and dimensional score surfaces
- user-facing taste memory and session-memory signals
- confidence-aware scoring explanations
- actions that let the user steer future recommendations

### Wave 6 - Curation Safety And Library Stewardship

Support the playlist-first intelligence system with trusted maintenance tools:

- duplicate review and keeper selection
- cleanup preview/apply flows
- rollback-aware curation operations
- enrichment-driven organization workflows

### Wave 7 - Packaged Confidence And Long-Session Stability

Keep release work in scope, but do not let it dominate product identity:

- packaged build validation
- installer proof on clean machine
- long-session playback/acquisition stability
- failure recovery and diagnostics

## Migration Discipline

When implementing a capability in Rust/Tauri/Svelte:

1. Check whether Python already solved the process logic or provider workflow.
2. Preserve the useful behavior, even if the runtime shape changes.
3. Reuse existing env/config/provider plumbing where possible.
4. Avoid fake clean-slate abstractions that ignore working integrations already present in the repo.

The migration goal is not "remove Python because it exists."
The migration goal is "port Lyra's real intelligence product into the canonical native runtime."
