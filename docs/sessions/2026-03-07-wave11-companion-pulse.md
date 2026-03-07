# Session Log - S-20260307-12

**Date:** 2026-03-07
**Goal:** Wave 11: event-driven companion pulse and native ritual affordances
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

Wave 10 (MBID Identity Spine) was landed and closed (S-20260307-11). 201 tests passing.
Background enrichment jobs were running (MBID resolve, structure analyze, biographer).
SPEC-011 was already written before this session's implementation began.

---

## Work Done

- [x] Created `oracle/companion/__init__.py` — module marker
- [x] Created `oracle/companion/pulse.py` — `CompanionPulse` class: subscribes to `PlayerEventBus` in a background thread, translates 5 player event types into 5 companion envelopes (`track_started`, `track_finished`, `queue_empty`, `paused`, `resumed`); external injection helpers `publish_provider_event` and `publish_acquisition_event`; process singleton `get_companion_pulse()`
- [x] Created `oracle/api/blueprints/companion.py` — `/ws/companion` SSE endpoint using same `stream_with_context` + `PlayerEventBus.subscribe()` pattern as `/ws/player`
- [x] Registered `oracle.api.blueprints.companion` in `oracle/api/registry.py` BLUEPRINTS list
- [x] Created `tests/test_companion_pulse.py` — 14 contract tests (5 test classes, all via `_translate()` directly without threading; also tests `publish_provider_event` and `publish_acquisition_event`)
- [x] Created `desktop/renderer-app/src/features/companion/useCompanionStream.ts` — React hook: `EventSource` to `/ws/companion`, reconnects with 3-second back-off on error, returns `CompanionPulseEvent | null`
- [x] Created `desktop/renderer-app/src/features/companion/companionLines.ts` — `COMPANION_LINES` authored string templates for all 8 event types; `resolveCompanionLine()` helper
- [x] Updated `desktop/renderer-app/src/features/companion/LyraCompanion.tsx` — imports `useCompanionStream` and `resolveCompanionLine`; `activeLine` derived from pulse event (falling back to static `mood.line`)
- [x] Updated `desktop/renderer-app/src/stores/settingsStore.ts` — added `notificationsEnabled: boolean` (default `false`) to `SettingsSnapshot`, `loadInitial()`, and store with `setNotificationsEnabled` action

---

## Commits

| SHA (short) | Message |
|---|---|
| `pending` | `[S-20260307-12] feat: Wave 11 companion pulse — event-driven companion SSE + frontend stream consumer` |

---

## Key Files Changed

- `oracle/companion/__init__.py` — new module
- `oracle/companion/pulse.py` — `CompanionPulse`, `get_companion_pulse` singleton
- `oracle/api/blueprints/companion.py` — `/ws/companion` SSE blueprint
- `oracle/api/registry.py` — `BlueprintSpec("oracle.api.blueprints.companion")` appended
- `tests/test_companion_pulse.py` — 14 contract tests
- `desktop/renderer-app/src/features/companion/useCompanionStream.ts` — SSE hook
- `desktop/renderer-app/src/features/companion/companionLines.ts` — authored line templates
- `desktop/renderer-app/src/features/companion/LyraCompanion.tsx` — consumes stream
- `desktop/renderer-app/src/stores/settingsStore.ts` — `notificationsEnabled` added
- `docs/PROJECT_STATE.md` — Wave 11 state update
- `docs/WORKLIST.md` — Wave 11 landed
- `docs/SESSION_INDEX.md` — row added

---

## Result

Wave 11 fully landed. `LyraCompanion` is now event-driven: it subscribes to `/ws/companion` and renders authored narrative lines from backend companion pulse events in real time. Static fallback is preserved when no event has arrived. `notificationsEnabled` setting is wired in to the store (notification delivery is the next additive step once Tauri plugin is available).

---

## State Updates Made

- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` — no new gaps opened; companion-as-ornament gap now closed
- [x] `docs/SESSION_INDEX.md` row updated
- [x] Tests pass: `python -m pytest -q` → 215 passed
- [x] Renderer: `npm run test` → 26 passed; `npm run build` → clean

---

## Next Action

Run additional `oracle mbid resolve` passes until recording_mbid coverage exceeds 50%, then run `oracle credits enrich --limit 500` for MBID-backed credit rows. Open Wave 12 when the next feature priority is settled.

