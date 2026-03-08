# Lyra

Lyra is a native desktop music player with:

- Tauri 2 shell
- SvelteKit frontend
- Rust application core
- SQLite local-first storage

The canonical app runtime is Python-free.

## Current Runtime

- Desktop shell: `desktop/renderer-app/src-tauri/`
- Frontend: `desktop/renderer-app/src/routes/`
- Rust core: `crates/lyra-core/`
- Local database: app-data SQLite owned by Rust

Legacy Python/oracle material remains in-repo as reference and migration source only. It is not part of normal startup, playback, queue, or library flow.

## Quick Start

```powershell
cd desktop\renderer-app
npm install
npm run check
npm run build
npm run tauri:dev
```

Rust validation from repo root:

```powershell
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
```

## What Works Now

- Tauri launches without Python
- SvelteKit desktop shell renders
- Rust command bridge owns app state
- SQLite init/open is Rust-owned
- Library roots persist locally
- Scan jobs import tracks into the Rust-owned catalog
- Playlists, queue, settings, provider config records, and legacy import path are wired
- Tray, menu, global shortcut, and window-state hooks exist in the native shell

## Legacy Import

Lyra can import supported provider settings from `.env` and selected content from `lyra_registry.db` into the Rust-owned runtime store.

Imported now:

- supported provider/API keys
- tracks
- saved playlists where shape is compatible
- queue/session state where available

Preserved but not migrated now:

- Chroma/vector state
- Python enrich cache internals
- acquisition job history
- oracle/recommendation internals

## Docs

- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/ARCHITECTURE.md`
- `docs/MIGRATION_PLAN.md`
- `docs/CANONICAL_PATHS.md`
