# CLAUDE.md - Persistent Memory for Lyra

Keep this file synchronized with repo truth.

## Read Order

1. `AGENTS.md`
2. `docs/LYRA_INTELLIGENCE_CONTRACT.md`
3. `docs/PROJECT_STATE.md`
4. `docs/WORKLIST.md`
5. `docs/MISSING_FEATURES_REGISTRY.md`
6. `docs/ROADMAP_ENGINE_TO_ENTITY.md`
7. `docs/SESSION_INDEX.md`

## Project Identity

Lyra is a vibe-to-journey music intelligence, discovery, and curation system with native playback.

The canonical runtime is:

- Tauri 2 desktop shell
- SvelteKit renderer in `desktop/renderer-app/`
- Rust core in `crates/lyra-core/`
- Rust-owned SQLite local store

Lyra is not a media player project with an AI sidebar.
Playback, queue, library, acquisition, and provider plumbing are support layers for:

- freeform intent interpretation
- explainable recommendation
- playlist authorship and sequencing
- bridge-track and adjacency discovery
- taste steering and memory

## Current Truth Snapshot (March 8, 2026)

- Canonical composer pipeline now exists in Rust/Tauri/Svelte as a first-pass slice:
  typed `PlaylistIntent`, local/cloud LLM provider abstraction, deterministic retrieval/reranking/sequencing, visible phase plan, and persisted reason payloads.
- Provider selection is now explicit in app settings and reuses existing provider config plumbing.
- Acquisition, provenance, and horizon work remain important, but they are infrastructure for Lyra identity rather than the identity itself.

Use `docs/PROJECT_STATE.md` for the audited state.

## Working Rules

- Treat `docs/LYRA_INTELLIGENCE_CONTRACT.md` as canonical for composer and LLM behavior.
- Do not flatten Lyra into “chat”, “search”, or “player polish”.
- Keep deterministic ranking and sequencing local; do not let LLMs invent library contents or final playlists.
- Keep docs aligned in the same pass whenever product truth changes.

## Session Close Requirements

When behavior changes:

1. Update `docs/PROJECT_STATE.md`
2. Update `docs/WORKLIST.md`
3. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap status changed
4. Update `docs/SESSION_INDEX.md`
5. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
6. Run validation
7. Run docs QA:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```
