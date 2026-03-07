# Renderer AGENTS

Read the repo-root `AGENTS.md` first. This file narrows the renderer lane.

## Scope

- React/Tauri renderer work under `desktop/renderer-app/`
- UI surfaces that expose real backend/recommendation/player state
- provenance/explainability presentation after prerequisite waves are unblocked

## Rules

- Preserve Tauri as the only supported desktop host path
- Keep Mantine as infrastructure, not the visible design authority, unless an existing surface already depends on it
- Prefer bespoke Lyra shell language over generic dashboard patterns
- Keep route and API truth aligned with backend contracts

## Do Not Do From This Lane

- Do not rewrite build/runtime authority from renderer code
- Do not start detached cosmetic churn that is not tied to user-visible value
- Do not touch installer/release-gate scripts from this lane
- Do not revert unrelated dirty-tree changes

## Validation

```powershell
cd desktop\renderer-app
npm run test
npm run build
powershell -ExecutionPolicy Bypass -File scripts\check_docs_state.ps1
```
