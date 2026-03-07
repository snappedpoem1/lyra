# Frontend Provenance Brief

Date: 2026-03-06
Wave: 6

This lane is blocked until the document/governance, build, runtime/data-root, and metadata/recommendation waves are merged.

## Scope Once Unblocked

- UI surfaces that expose recommendation rationale, provenance, confidence, and degraded states
- Oracle, playlist detail, right-rail detail, and now-playing insight depth
- visual/product depth that directly strengthens explainability and control

## Forbidden Until Unblocked

- do not treat this as a detached aesthetic rewrite
- do not change build/runtime authority here
- do not ship provenance UI before the payload contract exists

## Required Validation

```powershell
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

## Session Obligations

- open a dedicated session
- update state/worklist/session artifacts when user-visible truth changes
