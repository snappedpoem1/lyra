# Document and Governance Brief

Date: 2026-03-06
Wave: 1

Use this brief for documentation and coordination work only.

## Allowed Scope

- `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/MISSING_FEATURES_REGISTRY.md`
- `docs/SESSION_INDEX.md`
- `docs/sessions/*`
- `README.md`
- `AGENTS.md`
- `.github/copilot-instructions.md`
- `.github/instructions/*`
- `docs/agent_briefs/*`

## Forbidden Scope

- any Python, TypeScript, Rust, SQL, or PowerShell implementation files
- build-system changes
- installer/soak implementation work
- runtime behavior changes

## Required Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Obligations

- run `scripts/new_session.ps1` before edits
- update the matching session log
- update `docs/SESSION_INDEX.md`
- update authoritative docs in the same pass when repo truth changes
