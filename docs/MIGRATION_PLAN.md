# Migration Plan

## Why This Migration Exists

The migration is not just "remove Python."
It is "move Lyra's real music intelligence and curation product into a canonical native runtime."

Replaced active direction:

- Tauri host
- React renderer
- Python/Flask sidecar
- HTTP/SSE bridge
- Python-owned player/library/runtime logic

Current canonical direction:

- Tauri host
- SvelteKit SPA renderer
- Rust-owned core
- direct Tauri command/event bridge
- Rust-owned SQLite runtime

## What Stays True

- Python is not canonical runtime
- Rust/Tauri/Svelte remains the canonical runtime
- Existing Python logic is still a major migration source for solved process behavior
- Existing environment/config/provider plumbing should be reused and normalized, not recreated from scratch

## Legacy Surfaces And How To Treat Them

Legacy-heavy surfaces include:

- `oracle/`
- `lyra_api.py`
- Python-first startup/build scripts
- old React renderer moved under `desktop/renderer-app/legacy/react_renderer_reference/`

Do not reintroduce them into normal startup.
Do inspect them for:

- business logic already implemented
- provider interaction patterns
- queue/job/process flow
- explainability behavior
- playlist and discovery semantics
- configuration and secret-handling patterns already in production use

## Legacy Data Strategy

Preserved untouched:

- `.env`
- `lyra_registry.db`
- `chroma_storage/`

Imported now:

- supported provider/API keys from `.env`
- tracks from legacy SQLite
- saved playlists where shape is compatible
- queue/session state where possible

Not migrated yet:

- vector/chroma state
- richer Python enrich cache payloads
- acquisition history
- some oracle feedback, reason, and process internals

## Migration Work By Product Capability

### 1. Explainability And Provenance

- port recommendation evidence and reason-generation logic from Python
- expose provenance and confidence in canonical UI contracts
- promote MBID-first identity where available

### 2. Playlist Intelligence And Authorship

- port act and narrative playlist generation behavior
- persist reason payloads
- surface authored-journey explanations in Svelte UI

### 3. Discovery Graph And Bridge Exploration

- port graph builder, scout, and bridge-discovery logic
- bring graph-aware exploration into canonical routes
- connect discovery outputs to reasons and taste signals

### 4. Visible Taste And Dimensional Scoring

- port meaningful scorer/taste/backfill logic from Python
- expose score context honestly in canonical UI
- connect taste memory to recommendation and playlist flows

### 5. Curation And Library Stewardship

- port duplicates, cleanup, and rollback-aware curation workflows
- preserve process semantics already solved in Python

### 6. Acquisition And Ingest Intelligence

- preserve the working Python waterfall behavior until native parity exists
- port prioritization, guard, validator, and ingest-confidence logic deliberately
- keep acquisition connected to the broader intelligence layer

### 7. Packaged Desktop Confidence

- validate installer and packaged runtime
- complete soak testing
- close native release gate work without losing product-priority focus

## Configuration Migration Rule

Configuration is not a blank slate.
The codebase already contains:

- Python `.env` loading and path resolution
- Rust `.env` import and provider mapping
- provider config persistence in SQLite
- Rust provider validation
- keyring-backed secret handling

Migration work should consolidate those paths into the canonical runtime.
Do not replace them with fake placeholder config models.

## Execution References

- `docs/ROADMAP_ENGINE_TO_ENTITY.md` for sequencing
- `docs/WORKLIST.md` for active priority
- `docs/LEGACY_MIGRATION_REGISTRY.md` for migration-source mapping
- `docs/WORKFLOW_NEEDS.md` for workflow-level requirements
