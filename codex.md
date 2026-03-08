# Lyra Codex Guidance

This file is Codex-facing project context.
`AGENTS.md` remains the primary policy source and wins on conflicts.

## Canonical Product Truth

Lyra is a desktop-first, playlist-first, local-first music intelligence and curation system.

Lyra is not just a player.
The player is a foundation for the actual product shape:

- oracle-centered experience
- playlist-first workflow
- collapsible left library and navigation rail
- collapsible right context and inspector rail
- persistent mini player
- persistent Lyra input and composer line
- explainable recommendations
- bridge-track discovery
- visible "why this track?" behavior
- modular connected workspaces instead of disconnected pages

## Canonical Runtime Truth

The canonical runtime is:

- Tauri 2 desktop shell
- SvelteKit frontend in `desktop/renderer-app/`
- Rust application core in `crates/lyra-core/`
- SQLite local store owned by Rust

Python is not part of canonical startup, playback, queue, library, or normal player operation.
Do not frame Lyra as a Python/Flask/React/Vite app.
Do not reintroduce Python sidecars, localhost backend assumptions, or HTTP bridge assumptions into canonical runtime.

## Legacy Migration Truth

Legacy Python and oracle-era code is still important, but only as migration source.

Primary reference surfaces:

- `oracle/`
- `lyra_api.py`
- Python-first startup and build scripts
- `desktop/renderer-app/legacy/`

Use those surfaces to recover already-solved:

- acquisition workflow behavior
- retry and prioritization semantics
- enrichment provenance and confidence semantics
- explanation payloads and reason chains
- playlist-generation behavior
- graph and bridge discovery logic
- state machines and worker sequencing

Do not revive legacy runtime architecture as the solution.

## Legacy-to-Canonical Port Rule

Before implementing any missing canonical feature:

1. Inspect the relevant legacy Python and oracle-era code first.
2. Identify already-solved workflows, data shapes, retry logic, explanation payloads, ranking behavior, and lifecycle semantics.
3. Port the proven behavior deliberately into Rust, Tauri, and Svelte.
4. Do not recreate solved logic from memory.
5. Do not blindly clone legacy runtime architecture.
6. Document the source mapping from legacy behavior to canonical implementation in the relevant truth docs or session log.

The goal is behavior fidelity in the canonical runtime, not architectural nostalgia.

## Priority Order

Execution priority is locked to the current product needs:

1. `G-060` Acquisition workflow parity
2. `G-061` Enrichment provenance and confidence
3. `G-063` Playlist intelligence parity
4. `G-064` Discovery graph depth
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

This order exists to:

- harden workflow visibility and trust first
- expose provenance and identity confidence second
- restore playlist and oracle intelligence third
- deepen graph and bridge discovery fourth
- add safer curation workflows fifth
- leave packaging and soak as a bounded release gate last

## Canonical Shell Contract

The canonical product shell is part of the product truth, not optional polish.

The active app should keep these surfaces structurally present:

- collapsible left library and navigation rail
- center workspace for playlist, library, discovery, and acquisition work
- collapsible right inspector rail for context, explanation, provenance, bridge actions, queue, and acquisition state
- persistent Lyra input and composer line
- persistent bottom mini player

Do not implement new product behavior as disconnected pages that bypass this shell unless there is a hard technical blocker.
Future work for acquisition, provenance, playlist intelligence, discovery, and curation should publish into this shell rather than creating one-off UI islands.

## Implemented Now Vs Partial

Implemented now in the canonical runtime:

- Python-free Tauri boot
- Rust-owned SQLite runtime state
- library roots, scan/import, playlists, queue, settings, playback, and provider config records
- native playback controls and session restore foundation
- canonical app shell with collapsible rails, persistent mini player, and persistent Lyra composer line
- acquisition workflow baseline with staged lifecycle states, per-item progress and errors, queue controls, preflight checks, and surfaced lifecycle activity inside the shell
- partial recommendation, enrichment, artist, and taste surfaces

Still partial or scaffolded:

- enrichment provenance and confidence visibility
- playlist authorship and durable reasons
- graph and bridge discovery depth
- curation workflows with undo and rollback
- packaged desktop release confidence
- dedicated backend event streaming and final trust hardening for transitional acquisition bridge behavior

## Environment

- OS: Windows 11
- Shell: PowerShell
- Python path for legacy and transitional tooling: `.venv\Scripts\python.exe`
- Never delete or overwrite `lyra_registry.db`
- Never delete or overwrite `chroma_storage/`

## Coding Rules

- Use `pathlib.Path` in Python edits
- Use `logging.getLogger(__name__)` in Python edits
- Parameterized SQL only with `?`
- Type hints on every Python function signature
- New runtime behavior belongs in Rust
- Active UI behavior belongs in SvelteKit

## Ground Truth Read Order

1. `AGENTS.md`
2. `README.md`
3. `docs/PROJECT_STATE.md`
4. `docs/WORKLIST.md`
5. `docs/MISSING_FEATURES_REGISTRY.md`
6. `docs/ROADMAP_ENGINE_TO_ENTITY.md`
7. `docs/SESSION_INDEX.md`

## Session Protocol

Before behavior-changing work:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/new_session.ps1 -Slug "my-work" -Goal "What I am doing"
```

Use session-prefixed commits:

`[S-YYYYMMDD-NN] <type>: <description>`

## Validation

Run the canonical validation flow from repo root:

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

## Done Criteria

- canonical docs stay aligned with actual runtime truth
- session log and `docs/SESSION_INDEX.md` are updated
- changed behavior is validated honestly
- no fake completion claims
