# Scripts and Release AGENTS

Read the repo-root `AGENTS.md` first. This file narrows the scripts lane.

## Scope

- PowerShell automation under `scripts/`
- release-gate helpers
- launcher/build/validation scripts when that lane is explicitly assigned

## Rules

- Prefer deterministic, non-interactive scripts
- Keep logs and generated outputs behind declared runtime/build roots
- Record exact commands and environment assumptions in the matching session log when script behavior changes

## Do Not Do From This Lane

- Do not mix product/UI work into automation scripts
- Do not edit backend or renderer behavior unless the script change requires a paired contract update
- Do not touch installer/soak scripts during docs-only passes
- Do not revert unrelated dirty-tree changes

## Validation

Run the task-specific validation required by the active brief, plus:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```
