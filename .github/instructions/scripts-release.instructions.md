# Scripts and Release Lane Instructions

## Allowed Scope

- release-gate PowerShell scripts
- packaged runtime builders
- CI/release automation after the governance wave is merged

## Forbidden Scope

- do not begin this lane while document and governance hardening is still open
- do not mix product/UI work into release scripts
- do not touch installer/soak scripts during docs-only waves

## Required Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

Plus the specific release-gate validations required by the active brief.

## Session Obligations

- run `scripts/new_session.ps1`
- update roadmap/state/worklist/registry if build authority or release-gate truth changes
- record exact commands and environment in the matching session log
