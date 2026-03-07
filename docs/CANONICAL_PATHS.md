# Canonical Paths

This file defines the canonical, compatibility-only, and legacy/pending-archive paths for Lyra.

See `docs/ROADMAP_ENGINE_TO_ENTITY.md` § Surface Labels for label definitions.

## Canonical

| Surface | Path | Authority |
| --- | --- | --- |
| Desktop host | Tauri 2 (`desktop/renderer-app/src-tauri/`) | Only supported host path |
| Playback authority | Backend player domain (`oracle/player/*`) | Persisted `player_state` and `player_queue` |
| Playback transport API | `/api/player/*` | All UI transport actions route here |
| Player event stream | `/ws/player` (SSE) | Single canonical player event surface |
| UI structure | `docs/specs/SPEC-009_UI_STRUCTURE_SYSTEM.md` | Route archetypes, shell regions, semantic blocks |
| Data root / runtime | `LYRA_DATA_ROOT` via `oracle/config.py` | Writable-data authority (`%LOCALAPPDATA%\Lyra\dev` in dev) |
| Renderer | `desktop/renderer-app/` | React 18 + Vite + Tauri |
| Backend API | `oracle/api/` blueprints | Flask app via `oracle/api/__init__.py` |

## Compatibility Only

These paths are still functional but are not the preferred direction. They are not actively improved. They exist to avoid breaking existing workflows.

| Surface | Path | Notes |
| --- | --- | --- |
| Playback recording (legacy) | `/api/playback/record` | Kept for transition; use `/api/player/*` instead |
| BeefWeb bridge | `oracle/integrations/beefweb_bridge.py` | foobar2000 monitoring via BeefWeb REST API; not the canonical player |
| BeefWeb API endpoints | `GET /api/v1/beefweb/check`, `GET /api/v1/beefweb/now-playing` | Legacy integration endpoints in `oracle/api/blueprints/discovery.py` |
| BeefWeb CLI command | `oracle listen` | CLI bridge to foobar2000; not the canonical playback flow |
| Browser HTMLAudio | `audioEngine.ts` client-side audio | Non-canonical runtime behavior; backend player is canonical |
| Docker acquisition support | `docker-compose.yml`, `scripts/ensure_workspace_docker.ps1` | Optional for acquisition services; not required for daily playback |

## Legacy / Pending Archive

These paths are no longer functional or actively maintained. They should be archived or removed.

| Surface | Path | Status |
| --- | --- | --- |
| Electron host | Removed in Wave 2 (`S-20260306-23`) | Archived in `desktop/archive/electron.md`; git history retains code |
| Old renderer stub | `desktop/renderer/index.html` | Removed in Wave 16 cleanup |
| `desktop/extra/` | Empty folder | Removed in Wave 16 cleanup |
