# Docs and Governance Lane Instructions

## Allowed Scope

- roadmap/state/worklist/registry alignment
- session logs and session index
- README and root guidance files
- lane briefs and scoped instruction files

## Forbidden Scope

- code changes
- build script changes
- runtime behavior changes
- installer/soak implementation changes

## Required Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Obligations

- run `scripts/new_session.ps1`
- keep roadmap/state/worklist/registry mutually consistent
- update the matching session log and `docs/SESSION_INDEX.md`
