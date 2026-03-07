# Wave 15 — Codex Agent Brief (Parallel Lane)

**Session:** S-20260307-21  
**Date:** 2026-03-07  
**Role:** Parallel lane owner  
**Wave owner:** GitHub Copilot (backend fixes lane)  
**Protocol:** `docs/agent_briefs/tandem-wave-protocol.md`

---

## What Is Happening Right Now

Lyra Oracle has completed Waves 1–14. The last commit on `main` is `a34b6fb` (Wave 14: Saved Playlist UI).  
Current test baseline: **241 Python tests, 34 frontend (vitest) tests**, clean `npm run build`.

A backlog audit against the original ChatGPT planning documents (Phase 3–10 in `c:\chatgpt\`) revealed several planned features that were never implemented. This session splits that work across two agents running in parallel:

- **Copilot (wave owner):** backend-only lane — biographer stats bug, revelations metric, duplicates module, vibe→saved_playlists bridge
- **Codex (you, parallel lane):** frontend/Tauri native affordances lane — Wave 11-11C items

Do **not** edit the wave owner's claimed files (listed below as forbidden). Do **not** edit authoritative docs (`docs/PROJECT_STATE.md`, `docs/WORKLIST.md`, `docs/MISSING_FEATURES_REGISTRY.md`, `docs/SESSION_INDEX.md`) — the wave owner reconciles those at closeout.

---

## Mandatory Read Order

Before writing any code, read these files in order:

1. `AGENTS.md`
2. `docs/agent_briefs/tandem-wave-protocol.md`
3. `docs/ROADMAP_ENGINE_TO_ENTITY.md`
4. `docs/PROJECT_STATE.md`
5. `docs/WORKLIST.md`
6. `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` — UI structure authority
7. `docs/specs/SPEC-011_COMPANION_PULSE.md` — companion event contract (Wave 11 11A+11B already landed)
8. `desktop/renderer-app/AGENTS.md`

---

## Your Lane: Wave 11-11C — Native Ritual Affordances

Wave 11 split:
- 11A (landed): companion event spec  
- 11B (landed): companion pulse backend + `useCompanionStream.ts` + `companionLines.ts`  
- **11C (not started): native OS notifications, global shortcuts, small-state persistence**

### Priority Order

**P1 — Native OS notifications**  
Lyra already emits structured companion events over SSE at `/ws/companion`. When the app is in the background and a high-signal event fires, the user should get a native desktop notification.

Trigger events (from `SPEC-011`):
- `track_changed` — new track started
- `acquisition_complete` — a download finished
- `provider_degraded` — a provider went down

Implementation path:
- `desktop/renderer-app/src/features/native/useNativeNotifications.ts` — React hook that subscribes to companion SSE events and calls the Tauri notification API
- `desktop/renderer-app/src-tauri/src/` — ensure `tauri-plugin-notification` is registered in `main.rs` / `lib.rs` and declared in `tauri.conf.json` permissions
- Only fire when the window is not focused (check `appWindow.isFocused()` / `Window.isFocused()`)
- Notifications must be opt-in: gate behind a `LYRA_NATIVE_NOTIFICATIONS=true` env var or a `localStorage` user preference key `lyra:nativeNotifications`

**P2 — Global media key pass-through**  
Tauri already intercepts media keys in foreground. Wire global shortcuts so Play/Pause, Next, Previous work even when Lyra is in the background.

Implementation path:
- `desktop/renderer-app/src-tauri/src/` — register `tauri-plugin-global-shortcut` for `MediaPlayPause`, `MediaNextTrack`, `MediaPreviousTrack`
- Each shortcut handler should send an HTTP command to `http://127.0.0.1:{LYRA_PORT}/api/player/play|pause|next|previous`
- Shortcuts must be unregistered on app exit in the `on_window_event` / cleanup handler
- Port comes from `LYRA_PORT` env var (default `5000`)

**P3 — Small-state persistence across restarts**  
Currently the app loses sidebar collapse state, selected route, oracle panel open/closed state, and volume on every restart.

Implementation path:
- `desktop/renderer-app/src/features/native/usePersistentState.ts` — generic hook: `usePersistentState<T>(key: string, defaultValue: T)` that reads/writes to `localStorage` (acceptable for this use case — data is non-sensitive UI preference state)
- Apply to:
  - `UnifiedWorkspace.tsx` — oracle panel expanded/collapsed
  - `UnifiedWorkspace.tsx` — sidebar width or collapsed state if applicable
  - Volume level (currently held only in player state from backend; persist last-set frontend slider value under `lyra:volume`)
- Do **not** persist scroll position or query results — only small preference flags and the last-known route

---

## Owned Files (Codex)

You may freely create and edit these:

```
desktop/renderer-app/src/features/native/            ← new directory, all files yours
desktop/renderer-app/src-tauri/src/main.rs            ← shortcut + notification plugin registration
desktop/renderer-app/src-tauri/src/lib.rs             ← if plugin setup lives here instead
desktop/renderer-app/src-tauri/tauri.conf.json        ← plugin permissions declarations
desktop/renderer-app/src-tauri/Cargo.toml             ← add plugin crates
desktop/renderer-app/package.json                     ← add plugin npm packages if needed
```

You may **read but not edit** under your own initiative:
```
desktop/renderer-app/src/app/UnifiedWorkspace.tsx        ← read to understand oracle panel state
desktop/renderer-app/src/app/routes/                     ← read to understand route structure
desktop/renderer-app/src/services/lyraGateway/           ← read for API shape
```

---

## Forbidden Files (wave owner owns these)

Do **not** edit:

```
oracle/cli.py
oracle/api/blueprints/core.py
oracle/api/blueprints/vibes.py
oracle/duplicates.py                  ← wave owner will create this
oracle/api/blueprints/stats.py        ← wave owner may create this
tests/test_duplicates.py
tests/test_revelations.py
docs/PROJECT_STATE.md
docs/WORKLIST.md
docs/MISSING_FEATURES_REGISTRY.md
docs/SESSION_INDEX.md
```

---

## Coding Rules (always apply)

- `pathlib.Path` always, never `os.path`
- `logging.getLogger(__name__)` always, never `print()`
- Type hints on all function signatures
- No Docker dependency in any new code
- Follow `SPEC-009_UI_STRUCTURE_SYSTEM.md` for any UI placement decisions
- `snake_case` for files/functions, `PascalCase` for classes/components
- No new emotional dimensions — the 10 are fixed: `energy`, `valence`, `tension`, `density`, `warmth`, `movement`, `space`, `rawness`, `complexity`, `nostalgia`

---

## Validation

Before claiming your lane complete, run:

```powershell
cd desktop\renderer-app
npx vitest run
npm run build
npx tsc --noEmit
```

All three must pass. If new Tauri Rust code was added:

```powershell
cd desktop\renderer-app
npm run tauri:build -- --debug
```

**Do not** run the shared pytest suite — that is the wave owner's validation gate.

---

## Context Snapshot

| Metric | Value (March 7, 2026) |
|---|---|
| Tracks indexed | 2,455 |
| Python tests | 241 passing |
| Frontend tests | 34 passing |
| Last commit | `a34b6fb` Wave 14 |
| Companion pulse | Live — `/ws/companion` SSE, `useCompanionStream.ts`, `companionLines.ts` |
| Backend player | Canonical — `/api/player/*`, `/ws/player` SSE |
| Tauri version | 2.x (see `src-tauri/Cargo.toml`) |
| Node/npm | `.node-version` in repo root |
| Rust toolchain | `rust-toolchain.toml` in repo root |

---

## What Copilot Is Working On Simultaneously

(Do not touch these areas.)

1. **`oracle biographer stats` crash** — `UnboundLocalError` in `oracle/cli.py` at the `get_connection` bare usage inside the `stats` branch
2. **`GET /api/stats/revelations`** — new endpoint: recommended tracks that were saved + replayed within 7 days (the roadmap north-star metric from `docs/ROADMAP_ENGINE_TO_ENTITY.md §8`)
3. **`oracle/duplicates.py`** — new module for exact-hash and metadata fuzzy duplicate detection
4. **Vibe → `saved_playlists` bridge** — when `vibe.save=true`, mirror the vibe into `saved_playlists` + `saved_playlist_tracks` so it appears in `SavedPlaylistsSection`

---

## Done Criteria

This lane is complete when:

- `npx vitest run` passes (all existing + new tests)
- `npm run build` passes
- `npx tsc --noEmit` passes
- The native notification hook fires for `track_changed` / `acquisition_complete` / `provider_degraded` events
- Global media keys (play/pause, next, previous) work when app is backgrounded
- Oracle panel expanded/collapsed state survives an app restart
- No edits were made to the wave owner's forbidden file list

Update your own session log entries in `docs/sessions/2026-03-07-wave15-tandem.md` Work Done section when complete.
