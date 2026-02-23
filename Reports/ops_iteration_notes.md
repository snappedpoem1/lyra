# Lyra Ops Notes (Practical Order + Docs)

Generated: 2026-02-20

## Best Practical Order

1. Boot dependencies and verify health
   - Command: `python -m oracle.cli ops iterate --validation-limit 3 --report Reports/ops_iteration_check.md`
   - Purpose: baseline doctor + env scope + status/audit report before mutating library state.

2. White-glove validation baseline (one-time)
   - Command: `python -m oracle.cli validate --apply --workers 0 --confidence 0.7`
   - Behavior now: first full pass if no white-gloved tracks exist; later runs process only unvalidated tracks.

3. Canary acquisition + ingest
   - Command: `python -m oracle.cli ops iterate --no-bootstrap --validation-limit 1 --drain-limit 1 --watch-once --report Reports/ops_iteration_e2e.md`
   - Purpose: prove queue->download->ingest->index->status updates in one run.

4. Scaled batches
   - Command pattern: `python -m oracle.cli drain --limit 50 --workers 0` then `python -m oracle.cli watch --once`
   - Repeat with status/audit checks between batches.

## Environment Gaps Found

- LM Studio is offline and no executable auto-detected.
  - `LYRA_LM_STUDIO_EXE` is missing.
  - Current probe URL: `http://localhost:1234/v1/models`.
- Optional but recommended:
  - `HF_TOKEN` not set (Hugging Face warned during CLAP model operations).
  - `STAGING_FOLDER` not set (works via defaults, but explicit env reduces drift).

## External Docs Reviewed

- Docker Compose up reference:
  - https://docs.docker.com/reference/cli/docker/compose/up/
- LM Studio OpenAI-compatible local server docs:
  - https://lmstudio.ai/docs/developer/openai-compat
- LM Studio headless mode docs:
  - https://lmstudio.ai/docs/developer/core/headless
- Local Prowlarr API/docs endpoints used:
  - `http://localhost:9696/docs`
  - `http://localhost:9696/api/v1/indexer`
  - `http://localhost:9696/api/v1/indexer/schema`

## What Changed In Code During This Iteration

- Added operational automation + markdown reporting:
  - `oracle/ops.py`
  - `oracle/cli.py` (`ops iterate` command)
- Fixed false Docker offline in status command:
  - `oracle/cli.py` service check now runs `docker ps` correctly.
- Improved bootstrap reliability:
  - `oracle/bootstrap.py` now defaults to core services (`prowlarr`, `rdtclient`, `slskd`) and treats already-live services as ready.
  - Optional sidecar startup for Qobuz is now env-gated via `LYRA_BOOTSTRAP_QOBUZ=1`.
- Existing previous iteration changes remain active:
  - RuTracker setup command (`oracle prowlarr setup-rutracker ...`)
  - strict quality-only album replacement in catalog flow
  - white-glove validation tracking table + only-unvalidated default mode
