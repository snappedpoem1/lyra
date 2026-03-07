# Tandem Wave Protocol

Date: 2026-03-06
Status: active operating protocol

Use this brief when Codex and Copilot are both working on the same wave.

## Purpose

The goal is parallel speed without dirty-tree collisions, duplicate edits, or stale docs.

This protocol applies to implementation waves and to longer planning/design waves that feed them.

## Standing Roles

- `Wave owner`
  - owns the authoritative wave objective
  - owns final integration decisions for that wave
  - owns the sync-window updates to `docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, and `docs/SESSION_INDEX.md`
- `Parallel lane owner`
  - owns one bounded non-overlapping file set inside the same wave
  - must not edit the wave owner's claimed files unless the wave is explicitly re-split

These roles can switch between waves. They should not switch mid-wave unless the docs are updated first.

## Mandatory Preflight

Before either agent edits files:

1. Read:
   - `AGENTS.md`
   - `docs/ROADMAP_ENGINE_TO_ENTITY.md`
   - `docs/PROJECT_STATE.md`
   - `docs/WORKLIST.md`
   - `docs/MISSING_FEATURES_REGISTRY.md`
   - the active lane brief for the wave
   - this file
2. Open one session per agent with `scripts/new_session.ps1`.
3. Record in each session log:
   - the wave number
   - the agent role (`wave owner` or `parallel lane owner`)
   - owned files/directories
   - forbidden files/directories
   - required validation for that lane
4. Do not begin implementation until the owned file sets are disjoint.

## File Ownership Rules

- No shared editing of the same file in the same sync cycle.
- The wave owner owns the final edit to shared contract files.
- The parallel lane owner should prefer new files, isolated modules, isolated routes, isolated tests, or isolated scripts.
- If a change would require crossing into the other agent's claimed files, stop and re-split the wave in docs before proceeding.

## Sync Window Rules

Each shared wave has three sync windows:

1. Kickoff sync
   - claim files
   - agree on validation
   - confirm the next acceptance gate
2. Mid-wave sync
   - update session logs with real progress
   - surface blockers or boundary drift
   - reassign files only if needed
3. Closeout sync
   - wave owner reconciles authoritative docs
   - both agents finish session logs
   - shared acceptance commands are rerun

Outside sync windows, agents should not edit the authoritative docs at the same time.

## Validation Rules

- Each lane must run its own required validation before claiming completion.
- The wave owner reruns the shared acceptance gate before closing the wave.
- `powershell -ExecutionPolicy Bypass -File scripts/check_docs_state.ps1` is required at every closeout sync.

## Safe Split Pattern By Wave

### Wave 3 - Runtime and Data-Root Hard Cutover

Wave owner:
- `oracle/config.py`
- `lyra_api.py`
- `oracle/api/app.py`
- `oracle/runtime_state.py`
- `oracle/worker.py`
- runtime/data-root tests

Parallel lane owner:
- launcher and diagnostics surfaces:
  - `scripts/start_lyra_unified.ps1`
  - `oracle/doctor.py`
  - `oracle/runtime_services.py`
  - installed-layout/runtime validation helpers
- migration support docs and acceptance notes

Shared gate:
- backend pytest
- doctor/status checks
- docs-state check

### Wave 4 - Desktop Stack Modernization

Wave owner:
- Tauri host and dependency contract:
  - `desktop/renderer-app/src-tauri/*`
  - toolchain/host integration docs

Parallel lane owner:
- renderer adaptation lane:
  - `desktop/renderer-app/package.json`
  - `desktop/renderer-app/src/*`
  - renderer tests/build fixes

Shared gate:
- renderer test/build
- Tauri debug build
- docs-state check

### Wave 5 - Metadata, Recommendation, and Oracle Expansion

Wave owner:
- broker contract and API payload truth:
  - `oracle/recommendation_broker.py`
  - `oracle/api/blueprints/recommendations.py`
  - provider-contract tests

Parallel lane owner:
- provider/enrichment implementation:
  - `oracle/integrations/*`
  - `oracle/enrichers/*`
  - isolated provider adapters
  - Oracle action extensions that consume the new evidence

Shared gate:
- backend pytest
- provider contract coverage
- docs-state check

### Wave 6 - Product Surface Depth

Wave owner:
- API query/mapping and frontend contract glue:
  - query hooks
  - mappers
  - fixture/state shape alignment

Parallel lane owner:
- route/panel surfaces:
  - Oracle
  - playlist detail
  - right rail
  - now-playing insight panels
  - companion surfaces

Shared gate:
- renderer test/build
- docs-state check

### Wave 7 - Release-Gate Closure

Wave owner:
- soak runner, failure triage, packaged/runtime validation interpretation

Parallel lane owner:
- blank-machine installer proof
- evidence capture
- artifact/log collection
- closeout docs support

Shared gate:
- packaged-host proof
- installer proof
- 4-hour soak
- docs-state check

## Always-Open Safe Side Lane

One docs/research lane can stay open while another implementation wave is active if it stays inside:

- `docs/specs/*`
- `docs/research/*`
- the matching session log

That side lane must not rewrite authoritative runtime/build/worklist truth outside an agreed sync window.

## Done Criteria For A Shared Wave

A shared wave is done only when:

- both agent sessions are complete
- the authoritative docs reflect the integrated result
- overlapping placeholder rows or duplicate session records are cleaned up
- the wave owner confirms the acceptance gate passed after integration
