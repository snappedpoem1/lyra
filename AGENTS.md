Lyra is a vibe-to-journey music intelligence, discovery, and curation system with native playback, not a media player with AI features.

# AGENTS.md - Lyra Runtime Guidance

Read this file first. It is the authoritative entry point for repo-aware agents.

## Product Truth

Lyra is a desktop-first, playlist-first, local-first music intelligence and curation system.
Lyra is a vibe-to-journey system: the front door is creative intent, discovery, and guided curation, with playback acting as support infrastructure.

Playback matters, but playback is not the product differentiator.
Lyra exists to help a user understand, shape, and grow a music library through:

- explainable recommendation
- playlist authorship and act/narrative generation
- bridge-track and related-artist discovery
- visible emotional and dimensional taste signals
- provenance-aware and confidence-aware enrichment
- graph and constellation-style exploration
- a self-owned alternative to passive streaming algorithms

Canonical runtime:

- Tauri 2 desktop shell
- SvelteKit SPA frontend in `desktop/renderer-app/`
- Rust application core in `crates/lyra-core/`
- SQLite local store owned by Rust

Lyra is not a Python service in a desktop wrapper.
Python is not part of startup, playback, queue, library, or normal app operation.

## Runtime Rules

- No Python sidecar
- No localhost backend requirement
- No HTTP bridge for normal app function
- All active app commands flow through Tauri invoke/events
- Playback, queue, state, config, settings, provider config, and library ownership live in Rust

## Product Priority Rules

- Keep the canonical runtime intact: Tauri + SvelteKit + Rust + SQLite
- Treat playback/runtime correctness as foundation, not final identity
- Once the baseline is stable, prioritize identity-defining product capabilities before secondary polish:
  - playlist intelligence
  - explainability
  - discovery depth
  - taste tooling
  - provenance and confidence visibility
- Do not reduce Lyra to "just a correct local player" in docs, planning, or implementation framing

## Legacy Rule

Legacy Python/oracle code is not the canonical runtime, but it is still a primary migration source for:

- implemented business logic
- acquisition and enrichment process flow
- recommendation behavior
- playlist generation behavior
- graph and discovery workflow design
- solved operational patterns that should be ported, not rediscovered

Distinguish legacy Python surfaces carefully:

- obsolete runtime scaffolding
- still-valuable implemented logic
- feature behavior that must be preserved in migration
- config and provider plumbing already solved there

Reference-heavy surfaces include:

- `archive/legacy-runtime/oracle/`
- `archive/legacy-runtime/lyra_api.py`
- Python-first runtime/build scripts
- legacy renderer code moved under `desktop/renderer-app/legacy/`

Do not reintroduce those surfaces into canonical startup.
Do study them before replacing product logic or workflow behavior in Rust.

## Configuration And Secret Rules

- The repo and local environment already contain real provider/config wiring
- Reuse the existing environment/config/provider plumbing where possible
- Do not replace real config flows with placeholder architecture or fake examples
- Do not assume credentials are missing just because a feature is not yet surfaced in the canonical UI
- Do not print, log, summarize, commit, or otherwise expose secret values
- Do not rotate, overwrite, or invalidate credentials unless the user explicitly asks for that
- Normalize useful config and credential flows into Rust-owned provider config records and safe secret storage

## Ground Truth Files

- `README.md`
- `docs/LYRA_INTELLIGENCE_CONTRACT.md`
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
- Preserve playlist-first and intelligence-first product shape

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

Every behavior-changing or product-truth-changing session must:

1. Run `scripts/new_session.ps1`
2. Update `docs/sessions/YYYY-MM-DD-<slug>.md`
3. Update the matching row in `docs/SESSION_INDEX.md`
4. Update `docs/PROJECT_STATE.md` when runtime truth or honest capability state changed
5. Update `docs/WORKLIST.md` when next work changed
6. Update `docs/MISSING_FEATURES_REGISTRY.md` if a gap changed

Session ID format: `S-YYYYMMDD-NN`.
