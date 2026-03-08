# Renderer AGENTS

Read the repo-root `AGENTS.md` first.

## Scope

- SvelteKit frontend work under `desktop/renderer-app/`
- Tauri command/event integration from the UI layer
- Playlist-first desktop shell behavior

## Rules

- Treat SvelteKit as the canonical UI framework
- Do not reintroduce React runtime surfaces
- Do not assume HTTP, SSE, or localhost APIs
- Use Tauri invoke/events for app interactions
- Preserve the desktop shell structure:
  left rail, center content, right queue/context, bottom transport

## Do Not Do From This Lane

- Do not revive Python-backed bootstrap behavior
- Do not add browser-server assumptions or SSR dependency
- Do not revert unrelated dirty-tree changes

## Validation

```powershell
cd desktop\renderer-app
npm run check
npm run test
npm run build
cargo check --manifest-path src-tauri\Cargo.toml
```
