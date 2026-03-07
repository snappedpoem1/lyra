# Electron Archive

The Electron desktop lane was removed from active repo authority on 2026-03-06.

What changed:

- `desktop/package.json` is now a Tauri-only wrapper.
- Tracked Electron entrypoints (`desktop/main.js`, `desktop/preload.js`) were removed.
- Electron builder metadata and dependencies were removed from the tracked desktop package.

Historical Electron implementation remains available in git history before session `S-20260306-23`.