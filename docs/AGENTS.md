# Docs and Governance AGENTS

Read the repo-root `AGENTS.md` first. This file narrows the docs lane.

## Scope

- `docs/ROADMAP_ENGINE_TO_ENTITY.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`
- `docs/MISSING_FEATURES_REGISTRY.md`
- `docs/SESSION_INDEX.md`
- `docs/sessions/*`
- `README.md`
- lane briefs and governance/supporting docs

## Rules

- Keep roadmap, project state, worklist, and registry mutually consistent
- Treat docs/governance updates as a hard gate when execution order or repo truth changes
- When parallel agents are active, record lane boundaries explicitly instead of assuming them

## Do Not Do From This Lane

- Do not edit runtime code, build code, or product code unless the task explicitly exits the docs lane
- Do not touch installer/soak implementation from this lane
- Do not revert unrelated dirty-tree changes

## Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```
