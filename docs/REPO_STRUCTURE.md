# Repository Structure Contract

This file defines the intended source/runtime split so the repo stays maintainable.

## Source-first directories

- `oracle/` - Python domain, API blueprints, enrichment, search, scoring.
- `desktop/renderer-app/` - React renderer UI.
- `scripts/` - operational and validation scripts.
- `tests/` - Python and renderer contract tests.
- `docs/` - design notes, plans, and runbooks.

## Runtime and machine-generated directories

These are expected to change often and should not be treated as source truth:

- `chroma_storage/` - vector index runtime data.
- `data/` - provider/service state.
- `logs/` - runtime logs.
- `downloads/`, `staging/` - ingest/acquisition workspace.
- `backups/`, `_archive/` - point-in-time captures.

## Validation rule

Use these commands to verify source and runtime boundaries still hold:

```powershell
git status --short
.venv\Scripts\python.exe -m pytest -q
cd desktop\renderer-app; npm run test; npm run build
powershell -ExecutionPolicy Bypass -File scripts\smoke_desktop.ps1 -AllowLlmFailure
```

If these pass and `fixtureMode` is off in UI settings, the app is operating on live backend data rather than fixtures.
