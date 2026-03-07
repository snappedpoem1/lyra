# SPEC-003: `LYRA_DATA_ROOT` and Mutable Data Authority

## 1. Objective

Remove repo-root mutable-data assumptions and make one config-owned root authoritative for all writable runtime data.

The new authority is `LYRA_DATA_ROOT`.

This spec is for the Wave 3 runtime/data-root cutover and is intentionally independent from Wave 2 build-governance work.

## 2. Required Behavior

### 2.1 Single writable root

Introduce `LYRA_DATA_ROOT` as the primary root for mutable runtime data.

All writable defaults must derive from that root, including:

- SQLite registry database
- Chroma storage
- runtime state
- logs
- temp/scratch files
- model caches
- staging/downloads that are Lyra-owned runtime outputs
- any future persisted user-generated runtime state

### 2.2 Default resolution

Default behavior must differ by runtime context:

- Installed/package context:
  - default to `%LOCALAPPDATA%\Lyra`
- Development context:
  - default to `%LOCALAPPDATA%\Lyra\dev` unless explicitly overridden
- Tests:
  - always use isolated temp roots or test fixtures, never global defaults

`oracle/config.py` remains the single source of path truth.

### 2.3 Derived path contract

`LYRA_DATA_ROOT` is the primary authority.
All existing path settings become derived children or explicit overrides.

Expected derived layout:

- `LYRA_DATA_ROOT\db\lyra_registry.db`
- `LYRA_DATA_ROOT\chroma\`
- `LYRA_DATA_ROOT\logs\`
- `LYRA_DATA_ROOT\tmp\`
- `LYRA_DATA_ROOT\state\`
- `LYRA_DATA_ROOT\cache\hf\`
- `LYRA_DATA_ROOT\staging\`

Generated build artifacts under `.lyra-build` remain build outputs, not user data.

## 3. Compatibility and Migration

### 3.1 Detection

On startup, detect legacy repo-root mutable data locations if `LYRA_DATA_ROOT` does not already contain usable migrated state.

Legacy locations to detect include:

- `lyra_registry.db`
- `chroma_storage/`
- repo-root runtime-state files
- repo-root caches/logs if they still exist

### 3.2 Migration prompt

Do not migrate automatically without an explicit user confirmation step.

Required behavior:

1. Detect legacy data.
2. Show or log a migration-needed state.
3. Offer migrate now / defer.
4. If migrate now:
   - copy data into `LYRA_DATA_ROOT`
   - verify copied outputs exist
   - switch runtime to the new root
5. If defer:
   - require an explicit legacy override to continue using repo-root mutable data

### 3.3 Legacy override

Provide an explicit legacy compatibility flag/env only for temporary fallback.

This fallback must:

- be opt-in
- be clearly logged
- not become the silent default again

## 4. Implementation Requirements

### 4.1 Config layer

`oracle/config.py` must:

- resolve `LYRA_DATA_ROOT`
- derive child paths from it
- create required directories through one shared helper
- expose a stable API for all downstream modules

### 4.2 Consumers

Every module currently writing mutable defaults must be updated to use config-owned derived paths.

This includes, at minimum:

- backend startup/runtime
- worker paths
- doctor/status probes that write temp files
- embedders/model cache consumers
- runtime-state writers
- packaged-host startup environment

### 4.3 Installed/runtime contract

Installed runtime and packaged host flows must treat `LYRA_DATA_ROOT` as user data and `.lyra-build` as build/runtime artifact staging.

Do not mix them.

## 5. Non-Goals

- This spec does not change immutable packaged resources.
- This spec does not redesign library ownership paths outside Lyra-owned writable state.
- This spec does not migrate to a different database engine.

## 6. Validation

Required tests and checks:

1. Fresh dev launch uses `%LOCALAPPDATA%\Lyra\dev` by default.
2. Fresh installed-style launch uses `%LOCALAPPDATA%\Lyra`.
3. Legacy repo-root data is detected.
4. Migration copies database and Chroma content successfully.
5. Declined migration does not silently write back into repo-root defaults unless explicit legacy override is present.
6. Existing docs/doctor/status flows still work with the new root.
7. `scripts/check_docs_state.ps1` still passes after docs updates.

## 7. Acceptance Criteria

The cutover is complete when:

- repo-root mutable defaults are gone
- `LYRA_DATA_ROOT` is the documented authority
- installed and dev contexts resolve correctly
- migration behavior is explicit and safe
- runtime/source-separation docs can mark the authority gap materially reduced
