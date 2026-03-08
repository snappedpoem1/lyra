# Execution Plan (Goal Completion)

Last updated: March 8, 2026

This is the operational plan for finishing the remaining Lyra goals in canonical Rust/Tauri/Svelte surfaces.

## Planning Method

1. Build only canonical runtime (`crates/lyra-core`, `desktop/renderer-app`, `src-tauri`).
2. Use legacy Python and `C:\chatgpt` artifacts as reference requirements, not runtime dependencies.
3. Ship in bounded waves with explicit acceptance checks.
4. After each wave:
- run checks
- record findings
- update docs and next-wave scope

## Goal Tree

1. Workflow parity with legacy intent
- acquisition lifecycle
- enrichment provenance/confidence
- curation safety workflows
- playlist intelligence reasons
- discovery graph actions
2. Release confidence
- packaged installer proof
- long-session stability proof

## Wave Plan

## Wave Y (G-060): Acquisition Workflow Parity

### Deliverables

1. Lifecycle model per queue item: `acquire -> stage -> scan -> organize -> index`.
2. Event emission and persistence of lifecycle transitions.
3. Acquisition UI timeline/progress/error details.
4. Queue controls: retry failed, clear completed, prioritize.
5. Preflight checks: disk-space + required tools/provider readiness.

### Definition of Done

1. User can watch one item progress through all lifecycle states in UI.
2. Failed stage is visible with retry action and error reason.
3. Clear-completed and prioritize actions work and persist.
4. `cargo check --workspace` and `npm run check` pass.

## Wave Z (G-061): Enrichment Provenance & Confidence

### Deliverables

1. Provider-level confidence fields in enrichment payloads.
2. MBID-first identity display in Library and Artist views.
3. Enrichment lifecycle status (`not_enriched`, `enriching`, `enriched`, `failed`).
4. Force refresh with source-level status feedback.

### Definition of Done

1. User sees source + confidence for each enrichment provider.
2. Artist/track surfaces show MBID fields when available.
3. Failed provider states do not hide successful provider data.
4. Checks pass.

## Wave AA (G-062): Curation Workflows

### Deliverables

1. Duplicate cluster review with keeper selection.
2. Quarantine/delete execution with operation log.
3. Filename/path cleanup preview and apply flow.
4. Curation plan dry-run with rollback metadata.

### Definition of Done

1. User can resolve a duplicate cluster safely.
2. User can preview cleanup changes before apply.
3. Rollback data is stored for applied curation plans.
4. Checks pass.

## Wave AB (G-063): Playlist Intelligence Parity

### Deliverables

1. Run-based playlist generation with acts/phases.
2. Persisted track-level reason payloads.
3. Explainability UI: "why this track is here."
4. Save/apply generated run to playlist and queue.

### Definition of Done

1. Generated playlist has structured reasons for every track.
2. Reasons are retrievable and visible in UI.
3. User can save generated run and queue it directly.
4. Checks pass.

## Wave AC (G-064): Discovery Graph Depth

### Deliverables

1. Rich related-artist graph actions (`play similar`, `queue bridge`).
2. Discovery mode/source provenance display.
3. Session memory signals exposed and reused.

### Definition of Done

1. Artist page enables graph-driven playback actions.
2. Discover UI shows recommendation source/mode context.
3. Session signals influence and explain recommendations.
4. Checks pass.

## Wave AD (G-065): Release Gate

### Deliverables

1. `npm run tauri build` release bundle.
2. Blank-machine install and first-launch proof.
3. 4-hour audio soak with log capture.
4. Install/runtime failure checklist and closure.

### Definition of Done

1. Installer launch works on clean VM.
2. No blocking playback regressions during soak.
3. Documented release checklist is complete.

## Learning Loop

At the end of each wave:

1. Capture "what broke / what held / what to change next."
2. Convert findings into:
- one doc update (`PROJECT_STATE`, `WORKLIST`, `MISSING_FEATURES_REGISTRY`)
- one scoped next-wave delta
3. Keep wave scope fixed; move spillover to next wave.

## Validation Command Set

Run from repo root:

```powershell
cargo check --workspace
cd desktop\renderer-app
npm run check
```

Optional release gate:

```powershell
cd desktop\renderer-app
npm run tauri build
```

