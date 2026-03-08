# Migration Plan

## Replaced Architecture

Previous active direction:

- Tauri host
- React renderer
- Python/Flask sidecar
- HTTP/SSE bridge
- Python-owned player/library/runtime logic

Current replacement:

- Tauri host
- SvelteKit SPA renderer
- Rust-owned core
- direct Tauri command/event bridge
- Rust-owned SQLite runtime

## Preserved As Reference Only

- `oracle/`
- `lyra_api.py`
- legacy startup/build scripts for the Python path
- old React renderer moved under `desktop/renderer-app/legacy/react_renderer_reference/`

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

Not imported now:

- vector/chroma state
- Python-only enrich cache payloads
- acquisition history
- oracle feedback internals

## Remaining Migration Work

1. close acquisition workflow parity final contention (authoritative stage events from waterfall/native pipeline; UI controls are now wired)
2. complete enrichment workflow parity (source provenance, confidence, MBID-first views)
3. implement curation workflows (duplicate resolution, cleanup preview/apply, rollback metadata)
4. expand playlist intelligence (act-based generation + persisted reason payloads)
5. deepen discovery/artist graph workflows (play similar, bridge artists, source-aware discovery modes)
6. harden packaged desktop distribution after runtime stabilization

See `docs/WORKFLOW_NEEDS.md` for concrete workflow-level requirements.
Execution sequencing, dependencies, and wave acceptance criteria are defined in `docs/EXECUTION_PLAN.md`.
