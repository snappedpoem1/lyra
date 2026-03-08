# Worklist

Last updated: March 8, 2026

## Current State

- Rust, Tauri, and SvelteKit are the active runtime path.
- Python and oracle code are migration source only, not canonical runtime.
- The canonical shell contract is now real in code: collapsible rails, persistent mini player, and persistent Lyra composer line.
- G-060 is at a usable baseline inside that shell.
- Native playback, library, queue, settings, and provider plumbing are ahead of the remaining identity-depth lanes.

## Execution Rule

Do not spend time on lower-value branches while higher-value canonical identity work remains open.
Before implementing any missing feature, inspect the relevant legacy Python or oracle logic first and port the solved behavior deliberately.

## Priority Order

This ordering is locked:

1. `G-060` Acquisition workflow parity
2. `G-061` Enrichment provenance and confidence
3. `G-063` Playlist intelligence parity
4. `G-064` Discovery graph depth
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

Reason:

- harden workflow visibility and trust first
- expose provenance and identity confidence second
- restore playlist and oracle intelligence third
- deepen graph and bridge discovery fourth
- add safer curation workflows fifth
- keep packaging and soak bounded as the release gate last

## Active Lane

Execution details belong in `docs/ROADMAP_ENGINE_TO_ENTITY.md` and `docs/MIGRATION_PLAN.md`.
This file tracks the next highest-value canonical work only.

### G-061 Enrichment Provenance And Confidence

Goal: make enrichment and identity trust legible inside the canonical shell.

- [x] Add explicit provider and source display for enrichment outputs in the inspector and workspace surfaces
- [x] Add confidence visibility where enrichment materially affects decisions in Library and Artist views
- [x] Promote MBID-first identity fields in Library and Artist views
- [ ] Port useful provider evidence semantics from legacy enrichment flows before recreating UI behavior
- [ ] Reuse existing provider config and secret plumbing instead of parallel config paths
- [x] Keep provenance and confidence visible through the canonical shell rather than isolated detail panels
- [x] Extend first-pass provenance and confidence coverage into playlists and discovery surfaces
- [ ] Extend provenance and confidence coverage into saved playlists and broader recommendation explanation flows
- [ ] Keep degraded, missing, and not-configured provider states consistently honest across all shell surfaces

### G-060 Acquisition Workflow Parity Checkpoint

Current checkpoint: usable baseline implemented in the canonical shell.

- [x] Staged lifecycle coverage across `acquire`, `stage`, `scan`, `organize`, and `index`
- [x] Per-item progress, errors, and lifecycle notes visible in the Acquisition workspace
- [x] Queue lifecycle controls: retry failed items, clear completed items, and prioritize items
- [x] Preflight checks explicit for disk space and transitional downloader/tool availability
- [x] Lifecycle events surfaced in the Acquisition workspace and shell inspector
- [x] Legacy acquisition sources inspected before recreating queue behavior
- [ ] Keep hardening backend-driven event authority and remaining trust semantics without reopening lower-priority branches

### G-063 Playlist Intelligence Parity

Goal: restore playlist authorship as a first-class product behavior.

- [ ] Port act and narrative playlist generation behavior from legacy playlist and vibe logic
- [ ] Persist per-track reason payloads for generated playlists
- [ ] Add "Why is this track here?" UI for generated playlists and saved runs
- [ ] Keep playlist structure and authored reasoning durable when saving
- [ ] Inspect `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, and related blueprint flows first

### G-064 Discovery Graph Depth

Goal: make discovery feel like Lyra rather than a flat recommendation page.

- [ ] Port graph, constellation, and bridge-discovery logic from legacy discovery flows
- [ ] Add related-artist and bridge actions connected to reasons and provenance
- [ ] Add graph-backed exploration UI instead of flat lists only
- [ ] Add session-memory signals that influence and explain discovery outputs
- [ ] Inspect `oracle/graph_builder.py`, `oracle/scout.py`, and `oracle/recommendation_broker.py` first

### G-062 Curation Workflows

Goal: support safe stewardship of the library after the identity-defining lanes are stronger.

- [ ] Port duplicate review and keeper-selection workflows with undo
- [ ] Add cleanup preview and apply flows with rollback metadata
- [ ] Reuse existing Python curation semantics instead of inventing new ones
- [ ] Inspect `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py`, and ingest watcher behavior first

### G-065 Packaged Desktop Confidence

Goal: finish the release gate without letting it dominate roadmap identity.

- [ ] Run `npm run tauri build` release bundle with NSIS installer
- [ ] Validate on a clean Windows machine
- [ ] Run a 4-hour audio soak test
- [ ] Validate long-session stability and recovery
- [ ] Finish installer cleanup and error handling

## Cross-Cutting Rules

- [ ] Audit real Python implementations before porting missing canonical features
- [ ] Classify legacy modules into scaffolding vs migration-source logic as work proceeds
- [ ] Consolidate existing provider env, config, and keyring plumbing into canonical Rust and Tauri surfaces
- [ ] Avoid duplicate credential or config systems
- [ ] Keep secret handling safe in code, docs, logs, and summaries
