# Worklist

Last updated: March 8, 2026

## Current State

- Rust/Tauri/SvelteKit is the active runtime path.
- Python/oracle is not canonical runtime, but it still contains meaningful logic and workflow behavior that should inform migration.
- Native playback/library/queue/settings/provider plumbing are materially ahead of the user-facing intelligence layer.

## Priority Principle

Lyra is not mainly chasing workflow parity for its own sake.
The goal is to port and surface the product's actual differentiators inside the canonical runtime:

- explainable intelligence
- playlist authorship
- discovery depth
- visible taste tooling
- provenance-aware enrichment

## Next Up (Prioritized By Product Identity)

Execution details belong in `docs/ROADMAP_ENGINE_TO_ENTITY.md` and `docs/MIGRATION_PLAN.md`.
This file is the active lane.

### Wave Z: Explainability, Provenance, And Confidence - HIGH PRIORITY

**Goal**: Make the intelligence layer legible and trustworthy in the canonical app.

- [ ] Expand recommendation explanation coverage beyond the current limited surfaces
- [ ] Add explicit provenance/source display for recommendation and enrichment outputs
- [ ] Add confidence visibility where enrichment or recommendation scores are shown
- [ ] Promote MBID-first identity fields in Library and Artist views where available
- [ ] Audit Python explainability and provider-evidence logic before extending Rust contracts
- [ ] Reuse existing provider config/env plumbing instead of adding parallel config paths

### Wave AA: Playlist Intelligence And Narrative Generation - HIGH PRIORITY

**Goal**: Restore playlist authorship as a core product capability.

- [ ] Port act/narrative playlist generation behavior from existing Python playlist/vibe/oracle logic
- [ ] Persist per-track reason payloads for generated playlists
- [ ] Add "Why is this track here?" UI for generated playlists and saved runs
- [ ] Build save/apply flows that preserve playlist structure and authored reasoning
- [ ] Audit `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, and related blueprint flows before designing Rust replacements

### Wave AB: Discovery Graph And Bridge Actions - HIGH PRIORITY

**Goal**: Make discovery feel like Lyra, not a generic recommendation tab.

- [ ] Port graph/constellation logic from Python discovery and graph-builder surfaces
- [ ] Add related-artist and bridge-track actions that are visibly connected to reasons/provenance
- [ ] Add graph-backed exploration UI instead of flat related-artist lists only
- [ ] Add session-memory signals that influence and explain discovery results
- [ ] Audit `oracle/graph_builder.py`, `oracle/scout.py`, `oracle/recommendation_broker.py`, and community-weather integrations first

### Wave AC: Visible Taste And Dimensional Scoring - HIGH PRIORITY

**Goal**: Expose the internal taste model as something users can understand and steer.

- [ ] Port meaningful dimensional/emotional scoring logic from Python scorer/taste surfaces
- [ ] Show track-level and profile-level score context where it improves discovery and playlist decisions
- [ ] Add user-visible taste-memory/session-memory explanations
- [ ] Connect scoring surfaces to recommendation and playlist reasoning
- [ ] Audit `oracle/scorer.py`, `oracle/taste.py`, `oracle/taste_backfill.py`, and associated worker flows first

### Wave AD: Curation Workflow Port - MEDIUM PRIORITY

**Goal**: Support the intelligence system with safe curation and stewardship tools.

- [ ] Port duplicate review and keeper-selection workflows with undo
- [ ] Add cleanup preview/apply flows with rollback metadata
- [ ] Reuse existing Python curation logic where present instead of inventing new semantics
- [ ] Audit `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py`, and ingest watcher behavior before implementation

### Wave AE: Acquisition And Ingest Depth - MEDIUM PRIORITY

**Goal**: Keep acquisition aligned with intelligence and library confidence.

- [ ] Finish authoritative lifecycle/progress semantics for acquisition where still incomplete
- [ ] Port useful acquisition prioritization and ingest confidence behavior from Python
- [ ] Connect acquisition decisions to taste and discovery intent where justified
- [ ] Audit `oracle/acquirers/waterfall.py`, `oracle/acquirers/taste_prioritizer.py`, `oracle/ingest_watcher.py`, and validator/guard flows first

### Wave AF: Packaged Desktop Confidence - RELEASE GATE

**Goal**: Production-ready installer and long-session stability.

- [ ] Run `npm run tauri build` release bundle with NSIS installer
- [ ] Blank-machine validation on clean Windows VM
- [ ] 4-hour audio soak test
- [ ] Long-session stability validation
- [ ] Installer cleanup and error handling
- [ ] Auto-update mechanism

## Cross-Cutting Required Work

- [ ] Audit real Python implementations before porting identity features
- [ ] Classify Python modules into scaffolding vs migration-source logic as work proceeds
- [ ] Consolidate and normalize existing provider env/config/keyring plumbing into canonical Rust/Tauri surfaces
- [ ] Avoid introducing duplicate credential/config systems
- [ ] Keep secret handling safe: no secret values in docs, logs, commits, or summaries

## Quick Wins

- [ ] Install `fpcalc` on dev machine and validate AcoustID fingerprint round-trip
- [ ] Add session-key presence display to Last.fm settings
- [ ] Show artist/title in history panel instead of only track IDs
- [ ] Add keyboard shortcut documentation to Settings
- [ ] Implement "Recently Added" library filter

## Deferred But Documented

- vector and embedding migration strategy
- companion pulse system
- cloud backup/sync capability
- multi-platform support beyond current Windows-first execution reality
