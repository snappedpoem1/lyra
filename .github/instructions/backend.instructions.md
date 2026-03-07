# Backend Lane Instructions

## Allowed Scope

- Python backend domain logic
- API contracts and backend validation
- provider adapters after the governance, build, and runtime waves are unblocked

## Forbidden Scope

- do not start this lane while document and governance hardening is still open
- do not edit installer/soak scripts unless the active brief explicitly assigns that lane
- do not change roadmap/state/worklist/registry without updating docs in the same pass

## Required Validation

```powershell
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Obligations

- run `scripts/new_session.ps1`
- update `docs/sessions/*`
- update `docs/SESSION_INDEX.md`
- update authoritative docs first when repo truth changes
