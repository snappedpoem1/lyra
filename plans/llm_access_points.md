# LLM Access Points and Processing Map

## Purpose
This document maps where the local LLM is accessed and where LLM output is used in Lyra Oracle runtime flows.

## Primary Runtime Access Points

1. API health/status exposure
- File: `lyra_api.py`
- Path: `/health`, `/api/health`, and `/api/status`
- Behavior: Returns `llm` status payload via `oracle.llm.get_llm_status()`.
- Notes: Status is cached/lightweight in `oracle/llm.py` to avoid model thrash during polling.

2. Track classification second-pass
- File: `lyra_api.py`
- Path: `/api/curate/classify`
- Trigger: JSON body `{ "use_llm": true }`
- Processing:
  - Calls `oracle.classifier.classify_library(limit, use_llm=True)`
  - Invokes LLM only for ambiguous regex outcomes (`original` at `<=0.5`)
  - Records each attempt into `llm_audit` table
  - Returns counters: `llm_checked`, `llm_suggested`, `llm_applied`, `llm_errors`

3. Agent orchestration API
- File: `lyra_api.py`
- Paths:
  - `/api/agent/query`
  - `/api/agent/fact-drop`
- Processing:
  - Uses `oracle.agent.Agent`
  - Agent internally uses `oracle.llm.LLMClient` for intent parsing/tool orchestration
  - Falls back to deterministic heuristics when LLM unavailable

4. CLI search rewrite mode
- File: `oracle/cli.py`
- Command: `lyra search --nl "..."`
- Processing:
  - Uses `LLMClient.chat(...json_schema=...)` to rewrite user query into CLAP-friendly audio description

5. API search rewrite mode (ported)
- File: `lyra_api.py`
- Paths:
  - `/api/search` with `rewrite_with_llm=true` (or `natural_language=true`)
  - `/api/search/rewrite`
  - `/api/search/hybrid` with `rewrite_with_llm=true` (or `natural_language=true`)
- Processing:
  - Uses local LLM to rewrite raw query into CLAP-optimized audio description
  - Returns intent/rationale metadata and rewrite provenance
  - Falls back to raw query if LLM unavailable

6. Vibe generation + narration (ported)
- File: `lyra_api.py`
- Paths:
  - `/api/vibes/create` (one-shot create from prompt, optional build/materialize)
  - `/api/vibes/generate`
  - `/api/vibes/narrate`
- Processing:
  - Generate CLAP-friendly vibe query + name from prompt
  - Optional direct save to `vibe_profiles`/`vibe_tracks`
  - Generate short playlist arc narrative from vibe tracks

7. CLI curation classify with LLM
- File: `oracle/cli.py`
- Command: `lyra curate classify --llm`
- Processing:
  - Calls `classify_library(..., use_llm=True)`
  - Same second-pass + audit behavior as API route

8. Console agent command
- File: `oracle/console.py`
- Command: `lyra agent "..."`
- Processing:
  - Routes to `oracle.agent` and therefore into `LLMClient` orchestration path

## LLM Runtime + Bootstrap Infrastructure

1. LLM adapter and schema-constrained tasks
- File: `oracle/llm.py`
- Core functions:
  - `LLMClient.chat()`
  - `LLMClient.classify()`
  - `LLMClient.stream()`
  - `get_llm_status()`

2. LLM startup bootstrap (LM Studio)
- File: `oracle/bootstrap.py`
- Behavior:
  - Wakes LM Studio / `lms` server
  - Optionally auto-loads configured model
  - Returns readiness details used by CLI/API bootstrap paths

3. Unified launch bootstrap with fallback
- File: `Launch-Lyra.ps1`
- Behavior:
  - Tries LM Studio first
  - Falls back to Ollama
  - Starts Lyra API with selected provider/base_url/model exported to env

## Data Persistence Touchpoints

1. LLM classification audit trail
- Schema file: `oracle/db/schema.py`
- Table: `llm_audit`
- Producer: `oracle/classifier.py::_record_llm_audit`
- Captured fields:
  - regex result
  - llm result/category/confidence/reason
  - success/failure and whether result was applied

## Verification Workflow

Use the repeatable verification script:

```powershell
.venv\Scripts\python.exe scripts\verify_llm_usage.py --control-check
```

Success criteria:
- classify API returns HTTP 200
- `llm_checked > 0` for an ambiguous sample run
- `llm_audit` row count increases
- control run with `use_llm=false` does not write to `llm_audit`

## README/Docs Cross-Check Notes

1. README references LLM usage in:
- Agent endpoints and examples (`/api/agent/query`)
- Health payload (`health['llm']`)
- Environment variables (`LYRA_LLM_*`)
- LM Studio setup section

2. Architecture docs with LLM mentions:
- `plans/web_ui_implementation_plan.md` includes API surfaces for agent and classify flows
- `plans/system_architecture.md` currently describes core system but not detailed LLM pathing; this file fills that gap
