# Oracle Backend AGENTS

Read the repo-root `AGENTS.md` first. This file narrows the backend lane.

## Scope

- Python backend domain logic under `oracle/`
- Flask API behavior under `oracle/api/`
- backend tests under `tests/` when they validate backend behavior
- provider and enrichment work only after the governance, build, and runtime waves are unblocked

## Rules

- Use `pathlib.Path`, never `os.path`
- Use `logging.getLogger(__name__)`, never `print()`
- Use parameterized SQL only (`?`)
- Add type hints on all function signatures
- Keep runtime path authority in `oracle/config.py`
- Do not invent new emotional dimensions

## Do Not Do From This Lane

- Do not change roadmap/state/worklist/registry without updating docs in the same pass
- Do not touch installer/soak scripts unless the active brief explicitly assigns that lane
- Do not begin Wave 2+ work if the active docs/governance gate is not aligned
- Do not revert unrelated dirty-tree changes

## Validation

```powershell
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```

Add renderer validation only if a backend change also affects renderer-facing contracts and the task explicitly includes those surfaces.
