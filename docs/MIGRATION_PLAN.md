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

1. implement real Rust audio backend
2. improve library metadata import quality
3. port secure provider credential handling
4. port selected acquisition providers
5. port selected enrichment providers
6. rebuild oracle/recommendation features on Rust-owned contracts
7. harden packaged desktop distribution after runtime stabilization

