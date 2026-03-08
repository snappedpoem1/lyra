# AGENTS.md - Lyra Runtime Guidance

Read this file first. It is the authoritative entry point for repo-aware agents.

## Product Truth

Lyra is a desktop-first, playlist-first, local-first music player.

Canonical runtime:

- Tauri 2 desktop shell
- SvelteKit SPA frontend in `desktop/renderer-app/`
- Rust application core in `crates/lyra-core/`
- SQLite local store owned by Rust

Lyra is not a Python service in a desktop wrapper.
Python is not part of startup, playback, queue, library, or normal player operation.

## Runtime Rules

- No Python sidecar
- No localhost backend requirement
- No HTTP bridge for normal app function
- All active app commands flow through Tauri invoke/events
- Playback, queue, state, config, settings, provider config, and library ownership live in Rust

## Legacy Rule

Legacy Python/oracle code remains reference-only unless the user explicitly asks for migration or archival work on that material.

Reference-only surfaces include:

- `oracle/`
- `lyra_api.py`
- Python-first runtime/build scripts
- legacy renderer code moved under `desktop/renderer-app/legacy/`

Do not reintroduce those surfaces into canonical startup or docs.

## Ground Truth Files

- `README.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/CANONICAL_PATHS.md`
- `docs/ARCHITECTURE.md`
- `docs/MIGRATION_PLAN.md`
- `docs/LEGACY_MIGRATION_REGISTRY.md`
- `docs/SESSION_INDEX.md`

Rule: do not change runtime or product truth without updating the matching docs in the same pass.

## Coding Rules

- Use `pathlib.Path` in Python legacy edits; never `os.path`
- Use `logging.getLogger(__name__)` in Python legacy edits; never `print()`
- Parameterized SQL only
- Type hints on all Python signatures
- Rust owns new runtime behavior
- SvelteKit owns active UI behavior
- Preserve playlist-first product shape

## Canonical Surfaces

- Rust core: `crates/lyra-core/`
- Desktop app: `desktop/renderer-app/`
- Tauri host: `desktop/renderer-app/src-tauri/`
- Docs of truth: `docs/*.md` listed above

## Validation

Run from repo root on Windows:

```powershell
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cd desktop\renderer-app
npm run check
npm run test
npm run build
cargo check --manifest-path src-tauri\Cargo.toml
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Rules

Every behavior-changing session must:

1. Run `scripts/new_session.ps1`
2. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
3. Update the matching row in `docs/SESSION_INDEX.md`
4. Update `docs/PROJECT_STATE.md` when runtime truth changed
5. Update `docs/WORKLIST.md` when next work changed
6. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap changed

Session ID format: `S-YYYYMMDD-NN`.
