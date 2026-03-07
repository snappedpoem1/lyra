# Frontend Lane Instructions

## Allowed Scope

- React/Tauri renderer work
- provenance/explainability surfaces after prerequisite waves are unblocked
- UI modernization that preserves existing architectural truth

## Forbidden Scope

- do not start this lane while document and governance hardening is still open unless the task is docs-only
- do not rewrite build/runtime authority from the frontend lane
- do not perform detached cosmetic churn that is not tied to user-visible value

## Required Validation

```powershell
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Obligations

- run `scripts/new_session.ps1`
- update state/worklist/session artifacts when user-visible truth changes
- update docs first if roadmap/state/worklist/registry coordination changes
