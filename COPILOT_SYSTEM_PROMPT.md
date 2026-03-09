# Lyra Canonical Collaboration Prompt

Use this repo as Lyra, not as a Python-primary music tool.

## Product Truth

Lyra is a desktop-first, local-first, playlist-first music intelligence and curation system.

Canonical runtime:

- Tauri 2 desktop shell
- SvelteKit frontend in `desktop/renderer-app/`
- Rust core in `crates/lyra-core/`
- Rust-owned SQLite local store

Python is not the canonical runtime.
Legacy Python and oracle code remain in-repo as migration-source logic for solved workflows such as acquisition waterfall behavior, enrichment, recommendation, playlist intelligence, and discovery.

## Runtime Rules

1. Do not introduce a localhost backend dependency for normal app operation.
2. Do not re-center startup, queue, playback, settings, or library ownership around Python.
3. Route active behavior through Rust/Tauri commands and events.
4. Keep SvelteKit as the active UI layer.
5. Treat Python as reference logic to inspect before porting missing capability.

## Product Direction

Optimize for Lyra as:

- oracle-centered
- playlist-first
- explainable
- discovery-rich
- provenance-aware
- trustable during acquisition and curation

Avoid turning the app into:

- a generic admin dashboard
- a thin player shell
- a Python service in a desktop wrapper

## Migration Discipline

Before implementing a missing feature:

1. Inspect the relevant legacy Python/oracle code first.
2. Preserve the useful behavior, state semantics, and retry logic.
3. Port the behavior into Rust/Tauri/Svelte without reviving the legacy runtime shape.

## Docs Of Truth

Keep these aligned with code when product/runtime truth changes:

- `AGENTS.md`
- `README.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/MISSING_FEATURES_REGISTRY.md`
- `docs/ARCHITECTURE.md`
- `docs/CANONICAL_PATHS.md`
- `docs/MIGRATION_PLAN.md`
- `docs/ROADMAP_ENGINE_TO_ENTITY.md`
