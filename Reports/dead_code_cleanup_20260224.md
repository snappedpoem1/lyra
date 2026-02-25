# Dead Code Cleanup and Backend Boot Verification (2026-02-24)

## Scope
- Swept active backend code for high-confidence dead paths.
- Removed unused functions/constants that were no longer reachable.
- Added explicit dual-backend LLM boot verification.
- Re-ran backend QA + tests after cleanup.

## Removed/Refactored Dead Code

1. `oracle/acquisition.py`
- Removed unused helper:
  - `_update_status(...)`
- Reason:
  - All writes now flow through `_exec_write(...)` retry-safe transactions.
  - `_update_status` had no remaining call sites.

2. `oracle/agent.py`
- Removed legacy unused LLM code paths:
  - `_query_ollama(...)`
  - `_query_openai(...)`
- Removed unused legacy configuration constants:
  - `OLLAMA_BASE_URL`
  - `OLLAMA_MODEL`
  - `OPENAI_API_KEY`
  - `USE_OPENAI`
- Removed unused imports:
  - `os`
  - `requests`
- Updated module/help text to reflect current LLM integration through `oracle.llm` and `LYRA_LLM_*` settings.

## Launcher Hardening (LM Studio Boot Path)

`Launch-Lyra.ps1` was improved to make LM Studio boot behavior deterministic:
- Added `Get-LMStudioLoadedModels`
- Added `Get-LMStudioDiskModels` (via `lms ls --json`)
- Added `Try-LoadLMStudioModel` (via `lms load --yes <model>`)
- Updated `Try-BootLMStudio` to:
  - detect empty loaded-model state,
  - load preferred/disk model when possible,
  - fail with explicit reason if API is up but no model is loaded.

## New Verification Utility

Added:
- `scripts/verify_llm_backends.py`

What it checks:
- LM Studio backend:
  - `lms server status/start`
  - `http://127.0.0.1:1234/v1/models`
  - optional model load via `lms load --yes`
  - OpenAI-compatible ping through `oracle.llm`
- Ollama backend:
  - starts `ollama serve` if needed
  - `http://127.0.0.1:11434/v1/models`
  - ping through `oracle.llm`
  - unloads tested model after check (`ollama stop`)

Reports:
- `Reports/llm_backend_boot_latest.json`

## Current Backend Boot Status

Run:
- `python scripts/verify_llm_backends.py --ollama-model oracle-brain:latest --lmstudio-model qwen2.5-14b-instruct`

Result:
- `ollama`: **PASS**
- `lmstudio`: **FAIL**  
  Reason captured:
  - `Timed out waiting for LM Studio daemon to start.`
  - `Failed to start or connect to local LM Studio API server.`

This is currently an environment/runtime startup issue in LM Studio daemon, not an API integration code path issue.

## Validation After Cleanup

1. `python scripts/run_local_qa.py`
- Result: **PASS**

2. `pytest -q`
- Result: **PASS** (`15 passed`)

## Notes
- The dead code sweep intentionally avoided deleting backup/snapshot trees (`Backups/`, `_archive/`) and focused on active runtime modules only.
- No destructive operations were performed against user data paths.

---

## Second Sweep (2026-02-24, follow-up)

### Additional Cleanup Applied

Performed a repo-wide dead-code pass using:
- `python -m vulture oracle scripts lyra_api.py --min-confidence 80`
- `python -m ruff check oracle scripts lyra_api.py --select F401,F841`

Then applied safe removals:
- Removed 60+ unused imports (`F401`) across active modules via `ruff --fix`.
- Removed remaining unused locals (`F841`) in targeted files:
  - `oracle/acquirers/qobuz.py`
  - `oracle/architect.py`
  - `oracle/catalog.py`
  - `oracle/chroma_store.py`
  - `oracle/cli.py`
  - `oracle/curator.py`
  - `oracle/doctor.py`
  - `oracle/downloader.py`
  - `oracle/repair.py`
  - `scripts/lyra_acquire.py`
- Updated `oracle/downloader.py` mutagen capability probe to explicit `importlib.util.find_spec(...)` checks (keeps behavior, removes unused import artifacts).

Lint status after sweep:
- `ruff (F401,F841): PASS`

### Validation After Follow-up Sweep

Executed with project venv (`.venv\\Scripts\\python.exe`):
- `scripts/run_local_qa.py`: **PASS**
- `scripts/run_backend_surface_audit.py`: **PASS**
- `pytest -q`: **PASS** (`15 passed`)
- `scripts/run_stability_cycle.py`: **PASS**

### LLM Backend Boot Re-Verification

Enhanced:
- `scripts/verify_llm_backends.py`
  - attempts LM Studio local-service setting remediation,
  - attempts app launch fallback (`LM Studio.exe --headless`),
  - captures LM Studio log tail on failure for diagnostics.

Current status:
- Ollama: **PASS**
- LM Studio: **FAIL** (environment/runtime)

Observed blocker from LM Studio logs:
- `EPERM: operation not permitted, unlink 'C:\\Users\\Admin\\.lmstudio\\bin\\lms.exe'`
- Followed by daemon start timeout / unavailable local API.

Conclusion:
- Project-side boot logic and diagnostics are now hardened.
- Remaining LM Studio failure is external runtime state (CLI binary lock/update loop), not Lyra backend integration logic.
