# Lyra Oracle Batch-Clean Scope Overview (2026-02-24)

## Goal
Define what is required vs unnecessary if the app is used only for **batch cleaning an existing local library** (metadata cleanup, normalization, validation, repair), not for acquisition/discovery/agent features.

## Batch-Clean Definition
For this report, batch clean means:
- scan current library files
- normalize artist/title naming
- validate and enrich metadata
- repair broken DB entries and quality flags
- optional guard/audit cleanup over existing files
- no downloading, no LLM orchestration, no playlist/radio generation, no semantic search UX

## Keep (Core Required)
- `oracle/config.py`
- `oracle/db/schema.py`
- `oracle/scanner.py`
- `oracle/normalizer.py`
- `oracle/validation.py`
- `oracle/acquirers/validator.py`
- `oracle/repair.py`
- `oracle/name_cleaner.py`
- `oracle/doctor.py`
- `oracle/audit.py`
- `oracle/cli.py` subcommands to keep:
  - `db migrate`
  - `doctor`
  - `audit`
  - `status`
  - `scan`
  - `normalize`
  - `validate`
  - `repair`-related flows (currently via dedicated script)

## Keep Conditionally (Useful but not mandatory)
- `oracle/acquirers/guard.py`
- `oracle/acquirers/guarded_import.py`
- `oracle/download_processor.py`
- `scripts/repair_registry_entries.py`
- `scripts/check_errors.py`

Use these only if you still process a local `downloads/` staging area before merge into library.

## Not Necessary for Batch Clean (Disable First)
These are not required to clean existing local library data.

- Acquisition stack:
  - `oracle/acquisition.py`
  - `oracle/acquisition_search.py`
  - `oracle/downloader.py`
  - `oracle/hunter.py`
  - `oracle/catalog.py`
  - `oracle/lyra_protocol.py`
  - `oracle/acquirers/prowlarr_rd.py`
  - `oracle/acquirers/qobuz.py`
  - `oracle/acquirers/realdebrid.py`
  - `oracle/acquirers/spotdl.py`
  - `oracle/acquirers/waterfall.py`
  - `oracle/acquirers/ytdlp.py`
  - `oracle/acquirers/smart_pipeline.py`
  - `oracle/acquirers/prowlarr_setup.py`

- Discovery/experience stack:
  - `oracle/search.py`
  - `oracle/vibes.py`
  - `oracle/vibe_descriptors.py`
  - `oracle/radio.py`
  - `oracle/taste.py`
  - `oracle/scout.py`
  - `oracle/lore.py`
  - `oracle/dna.py`
  - `oracle/architect.py`
  - `oracle/agent.py`
  - `oracle/arc.py`
  - `oracle/console.py`
  - `oracle/ops.py`
  - `oracle/pipeline.py`
  - `oracle/safety.py`

- Embedding/scoring stack (not needed for strict cleaning):
  - `oracle/chroma_store.py`
  - `oracle/embedders/clap_embedder.py`
  - `oracle/indexer.py`
  - `oracle/scorer.py`
  - `oracle/anchors.py`
  - `oracle/fast_batch.py`

- LLM stack:
  - `oracle/llm.py`
  - LLM status and rewrite routes in `lyra_api.py`

## API Endpoints Not Necessary in Batch-Clean Mode
If running API-first batch clean only, keep only health/status and library maintenance routes.

Disable route groups:
- `/api/search*`
- `/api/vibes*`
- `/api/curate/*` except optional classify if you still use it
- `/api/acquire/*`
- `/api/downloads*` if no downloads staging
- `/api/spotify/*`
- `/api/scout/*`
- `/api/lore/*`
- `/api/dna/*`
- `/api/hunter/*`
- `/api/architect/*`
- `/api/radio/*`
- `/api/playback/*`
- `/api/agent/*`
- `/api/journal`, `/api/undo`
- `/api/pipeline/*`
- `/api/stream/*`

Keep:
- `/health`, `/api/health`
- `/api/status`
- `/api/library/scan`
- `/api/library/validate`
- `/api/library/tracks` (optional for inspection)

## Scripts Not Necessary for Batch Clean
- `scripts/lyra_acquire.py`
- `scripts/verify_llm_backends.py`
- `scripts/verify_llm_usage.py`
- `scripts/run_backend_surface_audit.py` (full-app audit, not clean-only)
- `scripts/run_stability_cycle.py` (full-app cycle)
- `scripts/test_embed.py`
- `scripts/diagnose_search.py`
- `scripts/diagnose_tiers.py` (unless troubleshooting acquisition services)
- `spotify_import.py`

## External Services Not Necessary
- Prowlarr
- Real-Debrid / rdtclient
- Slskd
- SpotDL backend runtime
- LM Studio / Ollama (unless explicitly used for metadata second-pass)
- ChromaDB runtime relevance for batch clean is minimal unless you keep semantic duplicate workflows

## Candidate Batch-Clean Profile
- Write mode: `apply_allowed`
- Enable:
  - scan
  - normalize
  - validate
  - repair
  - doctor/status
- Disable:
  - acquisition
  - llm
  - search/vibes/radio/agent
  - spotify imports
  - pipeline orchestration

## Practical Cleanup Sequence
1. Move non-batch scripts to `scripts/_archive/` or `scripts/optional/`.
2. Add a `BATCH_CLEAN_MODE=true` gate in `oracle/cli.py` and `lyra_api.py` to hide/deny non-clean commands/routes.
3. Split API startup into modular blueprints so batch-clean server only registers maintenance routes.
4. Remove service dependency checks in clean mode (`doctor` should not fail on Prowlarr/LM Studio when disabled).
5. Add dedicated smoke test set for clean mode only:
   - schema/migration
   - scan
   - normalize preview/apply
   - validate preview/apply
   - repair idempotence

## High-Value Immediate Wins
- Create a `oracle batch-clean` top-level command that executes:
  - `scan -> normalize (--apply optional) -> validate (--apply optional) -> repair`
- Lock out acquisition and LLM routes/commands in that mode to reduce failure surface and runtime cost.
- Keep full app as a separate profile rather than deleting modules immediately.
