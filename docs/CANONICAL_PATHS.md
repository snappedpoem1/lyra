# Canonical Paths

## Canonical

| Surface | Path | Authority |
| --- | --- | --- |
| Desktop host | `desktop/renderer-app/src-tauri/` | Tauri 2 shell |
| Rust core | `crates/lyra-core/` | App runtime authority |
| Frontend | `desktop/renderer-app/src/routes/` | SvelteKit UI |
| Local storage | app-data SQLite via `crates/lyra-core/src/db.rs` | Rust-owned source of truth |
| Command bridge | Tauri invoke/event flow | No HTTP runtime dependency |
| Product shell | Home, Library, Playlists, Queue, Settings | Playlist-first desktop structure |

## Compatibility Only

| Surface | Path | Notes |
| --- | --- | --- |
| Legacy config import | `.env` | Import source, not canonical runtime config |
| Legacy DB import | `lyra_registry.db` | Migration/reference source only |

## Legacy / Reference Only

| Surface | Path | Status |
| --- | --- | --- |
| Python runtime | `oracle/`, `lyra_api.py`, `archive/legacy-runtime/` | Not part of canonical runtime |
| React renderer | `desktop/renderer-app/legacy/react_renderer_reference/` | Preserved as reference |
| Python-first launcher scripts | `archive/legacy-runtime/` and related sidecar flows under `scripts/` | Reference only |
