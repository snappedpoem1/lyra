# Phase Execution Companion Through End Goal

Last updated: March 7, 2026

## 1) Purpose and Authority

This file is the execution-grade companion for Lyra's forward plan.

- `docs/ROADMAP_ENGINE_TO_ENTITY.md` remains the single forward-plan authority.
- This companion is the execution authority for phase sequencing, iteration order, handoff rules, and closeout expectations across the remaining program.
- Authoritative runtime/build/worklist truth is still reconciled only through the agreed sync windows described in `docs/agent_briefs/tandem-wave-protocol.md`.

Use this document when the question is "what phase are we in, what iteration comes next, who owns which lane, and what validation closes the phase?"

## 2) Current Baseline

Waves 1, 2, 3, and 4 are already landed locally.

- Wave 1 closed the governance-first gate:
  roadmap, state, worklist, registry, lane briefs, and scoped agent instructions are aligned.
- Wave 2 closed the build and release governance gate:
  Tauri is the only desktop authority, Windows-first CI and release gates exist, toolchains are pinned, and build provenance is emitted under `.lyra-build/manifests/`.
- Wave 3 closed the runtime/data-root gate:
  `LYRA_DATA_ROOT` is the mutable-data authority, explicit migrate-now/defer actions exist in CLI and runtime API, and the Wave 3 validation set passes locally.
- Wave 4 closed the desktop-stack gate:
  the host/runtime contract now runs on Tauri 2, renderer and host validation stayed green, and packaged-host smoke still passes against the Wave 3 runtime contract.

Active open gaps entering this companion:

1. Blank-machine installer install-and-launch proof is still pending outside this workstation and is blocked until a clean Windows machine or VM exists.
2. The full 4-hour parity/audio soak is still pending and is currently deferred until a later release-gate window.
3. Later metadata, recommendation, explainability, trust, and ritual-depth work remains intentionally gated behind the runtime and release-confidence phases.

Current execution begins at Wave 5.

## 3) Program Rules

1. No later phase starts before the current phase gate passes.
2. Shared phases use `docs/agent_briefs/tandem-wave-protocol.md`.
3. The wave owner owns final reconciliation of:
   - `docs/PROJECT_STATE.md`
   - `docs/WORKLIST.md`
   - `docs/MISSING_FEATURES_REGISTRY.md`
   - `docs/SESSION_INDEX.md`
4. Every phase closes with its phase validation plus:
   `powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1`
5. Existing specs remain authoritative where they already exist:
   - Wave 3 -> `docs/specs/SPEC-003_LYRA_DATA_ROOT.md`
   - Wave 5 -> `docs/specs/SPEC-004_RECOMMENDATION_PROVIDER_CONTRACT.md`
   - Wave 6 -> `docs/specs/SPEC-005_UI_PROVENANCE_AND_DEGRADED_STATES.md`
   - Wave 5 and later provider health expectations -> `docs/specs/SPEC-006_PROVIDER_HEALTH_AND_WATCHLIST.md`
6. Waves 8 through 11 each begin with a docs/spec iteration before implementation starts.
7. No phase may reintroduce Docker as a daily-playback dependency.
8. Spotify may remain auxiliary, but no future phase may treat Spotify as the strategic recommendation backbone.

## 4) Committed Phase Track

### Wave 1 - Document and Agent Hardening

Status:
- landed locally
- historical checkpoint only

Objective:
- establish the governance-first gate so later modernization work cannot drift

Gate:
- authoritative docs, lane briefs, and scoped agent instructions agree before any later modernization wave begins

Iterations:
- `1A` roadmap, state, worklist, and registry alignment
- `1B` scoped agent instructions and lane briefs
- `1C` tandem coordination protocol for later shared waves

Owner split:
- historical only; no active split required

Public contract changes carried forward:
- roadmap authority in `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- tandem-wave sync and ownership protocol

Acceptance:
- roadmap/state/worklist/registry aligned
- scoped guidance exists for root, backend, frontend, scripts, and docs lanes

Next trigger:
- Wave 2 may begin only after docs-state is clean and governance truth is aligned

Validation:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 2 - Build Simplification and Release Governance

Status:
- landed locally
- historical checkpoint only

Objective:
- make the Tauri/Windows release path the only supported desktop build and validation authority

Gate:
- Wave 1 closed and docs-state clean

Iterations:
- `2A` archive stale Electron authority
- `2B` establish Windows-first PR and release workflows
- `2C` pin toolchain authority and emit build provenance

Owner split:
- historical only; no active split required

Public contract changes carried forward:
- Tauri-only desktop authority
- Windows CI/release gate commands
- toolchain pins in `.python-version`, `.node-version`, and `rust-toolchain.toml`
- Windows artifact manifest output under `.lyra-build/manifests/`

Acceptance:
- Tauri is the only tracked desktop path
- CI and release governance run the validated Windows commands
- build manifest generation is wired into the release path

Next trigger:
- Wave 3 may begin only after the runtime/data-root contract is documented

Validation:
```powershell
python -m pytest -q
cd desktop\renderer-app
npm run test:ci
npm run build
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 3 - Runtime and Data-Root Hard Cutover

Status:
- landed locally
- historical checkpoint only

Objective:
- make `LYRA_DATA_ROOT` the only mutable-data authority and remove repo-root writable defaults

Gate:
- build and release governance is established
- the runtime and mutable-data contract is defined by `docs/specs/SPEC-003_LYRA_DATA_ROOT.md`

Iterations:
- `3A` config authority and derived path layout
- `3B` consumer cutover plus legacy detection, migrate/defer behavior, and explicit legacy override
- `3C` launcher, doctor, installed-layout validation, and docs reconciliation

Owner split:
- wave owner:
  - `oracle/config.py`
  - `lyra_api.py`
  - `oracle/api/app.py`
  - `oracle/runtime_state.py`
  - `oracle/worker.py`
  - runtime/data-root tests
- parallel lane:
  - `scripts/start_lyra_unified.ps1`
  - `oracle/doctor.py`
  - `oracle/runtime_services.py`
  - installed-layout/runtime validation helpers
  - migration support notes and acceptance notes

Public contract changes:
- `LYRA_DATA_ROOT` becomes the single writable-root authority
- derived writable layout:
  - `db\lyra_registry.db`
  - `chroma\`
  - `logs\`
  - `tmp\`
  - `state\`
  - `cache\hf\`
  - `staging\`
- explicit legacy detection, migrate/defer behavior, and opt-in legacy override
- `.lyra-build` remains build output only, not user data

Acceptance:
- dev defaults to `%LOCALAPPDATA%\Lyra\dev`
- installed and frozen defaults to `%LOCALAPPDATA%\Lyra`
- strict data-root validator passes
- backend pytest passes
- doctor and status pass
- docs-state passes

Next trigger:
- host/runtime modernization may begin only after Wave 3 closes

Validation:
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m oracle.doctor
.venv\Scripts\python.exe -m oracle.status
powershell -ExecutionPolicy Bypass -File scripts\validate_data_root_contract.ps1
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 4 - Desktop Stack Modernization

Status:
- landed locally
- historical checkpoint only

Objective:
- modernize Tauri and renderer dependencies without breaking the packaged host contract

Gate:
- Wave 3 runtime/data-root contract is stable enough to carry forward into host/runtime validation

Iterations:
- `4A` toolchain and dependency uplift plus compatibility fixes
- `4B` renderer adaptation and host bridge cleanup
- `4C` packaged-host revalidation on the upgraded stack

Owner split:
- wave owner:
  - `desktop/renderer-app/src-tauri/*`
  - toolchain and host integration docs
- parallel lane:
  - `desktop/renderer-app/package.json`
  - `desktop/renderer-app/src/*`
  - renderer tests and build fixes

Public contract changes:
- upgraded host/runtime dependency contract
- upgraded renderer dependency contract
- no change to the canonical backend-player authority

Acceptance:
- renderer tests and build pass
- Tauri debug build passes
- packaged host smoke still passes against the Wave 3 runtime contract

Next trigger:
- Wave 5 may begin only after the upgraded host/build/runtime path stays green

Validation:
```powershell
cd desktop\renderer-app
npm run test:ci
npm run build
npm run tauri:build -- --debug
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\packaged_host_smoke.ps1 -HealthTimeoutSeconds 45
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 5 - Provider Contract and Recommendation Core

Objective:
- implement the versioned provider and evidence contract with explicit degradation behavior from `SPEC-004` and `SPEC-006`

Gate:
- host, build, and runtime foundations remain green after Waves 3 and 4

Iterations:
- `5A` normalized adapter contract and broker versioning for existing providers
- `5B` provider reports, degradation summaries, and provider-health summaries
- `5C` evidence preservation, duplicate merge behavior, and feedback contract hardening

Owner split:
- wave owner:
  - broker and API payload truth
  - provider-contract tests
- parallel lane:
  - provider adapters
  - enrichers
  - isolated Oracle action consumers of the new evidence

Public contract changes:
- versioned broker payload:
  - `schema_version`
  - `seed`
  - `provider_reports`
  - `recommendations`
  - `degraded`
  - `degradation_summary`
- normalized evidence item contract
- provider-health summary contract:
  - `provider`
  - `enabled`
  - `status`
  - `last_success_at`
  - `last_error_at`
  - `last_error_summary`
  - `rate_limit_state`
  - `cache_state`

Acceptance:
- provider-level success, empty, degraded, and failed states are visible in API output
- merged recommendations preserve evidence and provenance
- diagnostics can surface provider health without requiring another contract rewrite

Next trigger:
- Wave 6 may begin only after provenance and degradation data is directly consumable by the UI

Validation:
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m oracle.doctor
.venv\Scripts\python.exe -m oracle.status
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 6 - Product Explainability Surfaces

Objective:
- render provenance, confidence, and degraded states directly in the key UX surfaces from `SPEC-005`

Gate:
- recommendation and provider evidence is available to surface without extra UI inference

Iterations:
- `6A` query and mapping glue for provenance payloads
- `6B` Oracle, playlist detail, right rail, and now-playing surfaces
- `6C` compact defaults plus expandable technical trace/details

Owner split:
- wave owner:
  - API mapping and query shape
  - fixture and state-shape alignment
- parallel lane:
  - route and panel surfaces

Public contract changes:
- provenance and degraded-state rendering expectations become active product requirements
- recommendation cards and rows support:
  - provider chips
  - confidence labels or bands
  - plain-language "why this"
  - degraded-state warnings
  - expandable technical trace/details

Acceptance:
- provider chips, confidence labels, plain-language rationale, and degraded states render from API output alone
- renderer tests and build pass
- docs-state passes

Next trigger:
- Wave 7 may begin only after explainability surfaces are live on the key recommendation paths

Validation:
```powershell
cd desktop\renderer-app
npm run test:ci
npm run build
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 7 - Release-Gate Closure

Objective:
- close the installer/runtime confidence gap and the production audio confidence gap

Gate:
- all earlier waves are landed and documented

Iterations:
- `7A` blank-machine installer proof with evidence capture
- `7B` 4-hour parity and audio soak on the finalized packaged/runtime contract
- `7C` integrated closeout and active-gap restatement or closure

Owner split:
- wave owner:
  - soak runner
  - failure triage
  - packaged/runtime validation interpretation
- parallel lane:
  - blank-machine installer proof
  - evidence capture
  - artifact and log collection
  - closeout docs support

Public contract changes:
- release-gate evidence becomes part of the trusted desktop product definition
- no new API surface is required, but the packaged runtime contract is now treated as production truth

Acceptance:
- real clean-machine install and first launch succeed
- 4-hour soak completes with acceptable evidence and no hidden backend masking
- `G-035`, `G-036`, and `G-039` are either closed or explicitly restated with evidence

Next trigger:
- Wave 8 may begin only after the installed product is credible enough to deepen trust and intelligence work

Validation:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaged_host_smoke.ps1 -HealthTimeoutSeconds 45
powershell -ExecutionPolicy Bypass -File scripts\validate_installed_runtime.ps1 -HealthTimeoutSeconds 45
powershell -ExecutionPolicy Bypass -File scripts\parity_hardening_acceptance.ps1 -SkipSidecarBuild -SoakSeconds 14400 -StartupTimeoutSeconds 60
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 8 - Ingest Confidence and Normalization

Objective:
- turn acquisition trust into a visible lifecycle instead of hidden background plumbing

Gate:
- release-gate closure is complete and the packaged/runtime contract is stable

Iterations:
- `8A` write and land a new spec for the ingest-confidence state machine before code
- `8B` promote validator, AcoustID, MusicBrainz, and bounded beets normalization into explicit backend phases with reason codes
- `8C` surface ingest state and trust outcomes in diagnostics and user-facing status

Owner split:
- wave owner:
  - ingest-confidence spec and backend lifecycle authority
  - state-machine tests and status truth
- parallel lane:
  - validator and enrichment integrations
  - diagnostics surfaces
  - user-facing status consumers

Public contract changes:
- ingest lifecycle states:
  - `acquired`
  - `validated`
  - `normalized`
  - `enriched`
  - `placed`
- validation and normalization reason codes
- anti-garbage confirmation evidence surfaced as first-class trust signals

Acceptance:
- acquired items can show where they are in the trust pipeline
- duplicate and mismatch handling becomes explainable instead of implicit
- trust failures are visible in diagnostics and status outputs

Next trigger:
- Wave 9 may begin only after acquisition trust is visible, not inferred

Validation:
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m oracle.doctor
.venv\Scripts\python.exe -m oracle.status
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 9 - Scout and Community Weather

Objective:
- make discovery more time-aware and make Scout a first-class provider and mode

Gate:
- ingest trust and normalized provider contracts are stable enough to broaden recommendation intelligence

Iterations:
- `9A` write and land a new spec for Scout plus community-weather provider behavior
- `9B` expand ListenBrainz inputs with fresh releases, similar users, and tag/radio motion
- `9C` promote Scout into the broker and Oracle as controlled-surprise discovery

Owner split:
- wave owner:
  - discovery-spec authority
  - broker and Oracle mode truth
  - contract tests
- parallel lane:
  - ListenBrainz expansion
  - Scout adapter work
  - supporting Oracle and library consumers

Public contract changes:
- provider keys and evidence types for Scout and community-weather signals
- Oracle mode and state additions for bridge-discovery flows
- time-aware discovery evidence alongside static similarity evidence

Acceptance:
- discovery can express current motion as evidence instead of only static similarity
- Scout is visible in recommendation and Oracle flows, not stranded as a side utility

Next trigger:
- Wave 10 may begin only after identity and cultural context can build on the expanded provider layer

Validation:
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m oracle.doctor
.venv\Scripts\python.exe -m oracle.status
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 10 - MBID Identity Spine and Live Orbit

Objective:
- consolidate identity around MusicBrainz and Cover Art Archive and add optional live-culture context

Gate:
- provider-contract and discovery layers are stable enough to carry richer identity and live-evidence work

Iterations:
- `10A` write and land a new spec for MBID-centric identity plus live-orbit data use
- `10B` unify release-group, work, artwork, and lineage context around MBIDs
- `10C` add optional Ticketmaster and setlist.fm evidence layers to artist and detail surfaces

Owner split:
- wave owner:
  - identity-spec authority
  - MBID contract and canonical payload truth
  - identity tests
- parallel lane:
  - live-culture adapters
  - enrichment helpers
  - artist/detail consumers

Public contract changes:
- MBID-centric identity payloads
- release-group, artwork, lineage, and live-orbit evidence items
- optional live-culture evidence that remains additive rather than mandatory

Acceptance:
- identity, artwork, and lineage stop being fragmented across ad hoc enrichers
- live context stays additive and never becomes mandatory for recommendation quality

Next trigger:
- Wave 11 may begin only after identity and cultural context are coherent enough to drive ritual surfaces

Validation:
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m oracle.doctor
.venv\Scripts\python.exe -m oracle.status
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

### Wave 11 - Companion Pulse and Native Ritual

Objective:
- finish the product end state by making the companion event-driven and the desktop experience instrument-like

Gate:
- identity, explainability, and release confidence are all stable enough to support ritual-depth work

Iterations:
- `11A` write and land a new spec for companion event surfaces and native ritual affordances
- `11B` drive the companion from structured player, recommendation, provider-health, and acquisition events
- `11C` add selected native affordances: notifications, global shortcuts, cleaner small-state persistence; updater only after release identity remains stable

Owner split:
- wave owner:
  - companion event contract
  - native ritual contract
  - product-depth acceptance truth
- parallel lane:
  - companion surface implementation
  - native notification, shortcut, and state-persistence integration
  - supporting diagnostics and settings surfaces

Public contract changes:
- companion and native ritual event families:
  - player events
  - recommendation events
  - provider-health events
  - acquisition events
- bounded native-state persistence contract

Acceptance:
- the companion feels like Lyra Pulse, not ornamental shell chrome
- desktop-native features strengthen trust, ritual, or continuity instead of generic app chrome

Next trigger:
- program closeout and end-state review

Validation:
```powershell
cd desktop\renderer-app
npm run test:ci
npm run build
npm run tauri:build -- --debug
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## 5) Cross-Phase Exit Condition

This phase track is complete when Lyra is:

- a stable installed desktop product
- running on a trusted packaged runtime contract
- explainable in its recommendations and degraded states
- explicit about acquisition trust and ingest confidence
- aware of cultural and live context without becoming trend noise
- driven by event-based ritual surfaces rather than ornamental chrome

At that point, Lyra has reached the intended end state for this companion:
one local-first music entity with trustworthy playback, explainable discovery, explicit trust layers, and durable desktop ritual.

## Immediate Start

Begin with `Wave 5 / Iteration 5A`: keep the settled Wave 4 host/runtime contract fixed, preserve the deferred release-gate items as separate blocked/deferred work, and open the provider-contract recommendation lane against `SPEC-004`.
