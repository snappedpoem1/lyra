# SPEC-011 — Companion Pulse and Native Ritual

**Wave:** 11  
**Session:** S-20260307-12  
**Status:** Accepted  
**Author:** Lyra Oracle  

---

## 1. Problem Statement

`LyraCompanion.tsx` already exists and renders correctly, but it is **static** — its mood and line text are derived purely from the current playback status string. It does not:

- React to track changes, queue state, recommendation results, provider health, or acquisition events
- Produce contextual lines or actions driven by real backend state
- Distinguish between "just started a new track" vs "same track, still playing"
- Surface any interesting moment (new recommendation ready, provider degraded, acquisition queued)

The companion is *ornamental* instead of *purposeful*. Wave 11 makes it event-driven.

---

## 2. Goals

1. **Backend**: A `CompanionEventBus` that listens to the existing `PlayerEventBus` plus recommendation, provider-health, and acquisition signals, and emits structured `companion_pulse` event envelopes over a new SSE endpoint `/ws/companion`.
2. **Frontend**: `LyraCompanion.tsx` subscribes to `/ws/companion` and renders contextual lines and action affordances from the event stream instead of static derived text.
3. **Native ritual affordances**: desktop OS notifications on track change (when companion is enabled and window is not focused) — additive only, guarded by a settings toggle.

**Non-goals:**

- No LLM narration or generated text — all lines are authored templates driven by event types.
- No modal or overlay interruption — companion stays in its panel region.
- No mandatory notification permission prompt — opt-in via settings toggle.

---

## 3. Architecture

### 3.1 Event types

```
companion_pulse
    event_type: str   # one of the values below
    context:    dict  # event-specific payload
    at:         float # unix timestamp
```

| `event_type` | Trigger | Context fields |
|---|---|---|
| `track_started` | `player_track_started` on the player bus | `artist`, `title`, `album` |
| `track_finished` | `player_track_finished` | `artist`, `title` |
| `queue_empty` | `player_track_finished` + empty queue | — |
| `paused` | `player_state_changed` with status=paused | — |
| `resumed` | `player_state_changed` with status=playing after paused | — |
| `recommendation_ready` | new recommendation result available | `count`, `top_artist` |
| `provider_degraded` | provider health state → degraded/unavailable | `provider`, `reason` |
| `provider_recovered` | provider health state → ok | `provider` |
| `acquisition_queued` | new track added to acquisition queue | `artist`, `title` |

### 3.2 Backend: `oracle/companion/pulse.py`

```
class CompanionPulse:
    subscribe() → Queue           # returns a queue for SSE consumers
    unsubscribe(queue)
    _on_player_event(event)       # called when player bus publishes
    start()                       # starts background listener thread
    stop()
```

`CompanionPulse` wraps `PlayerEventBus.subscribe()` in a background thread, translates player events into `companion_pulse` envelopes, and re-publishes them through its own fan-out bus (same `PlayerEventBus` pattern, reuse the class).

### 3.3 Backend: new SSE endpoint `/ws/companion`

```
GET /ws/companion
```

Same pattern as `/ws/player` — returns `text/event-stream`, subscribes to `CompanionPulse`, streams `data: <json>` lines, unsubscribes on close.

### 3.4 Frontend: `useCompanionStream` hook

```typescript
useCompanionStream(): { lastEvent: CompanionPulseEvent | null }
```

Connects to `/ws/companion`, maintains `lastEvent` state, reconnects on failure. Replaces the static `companionMood()` derivation in `LyraCompanion.tsx`.

### 3.5 Frontend line templates

All strings are authored constants in `companionLines.ts`:

```typescript
const COMPANION_LINES: Record<string, (ctx: Record<string, string>) => string> = {
  track_started: ({ artist, title }) => `Now: ${artist} — ${title}`,
  track_finished: ({ artist }) => `${artist} just completed.`,
  queue_empty: () => "The queue is open. Oracle is ready.",
  paused: () => "Queue held in orbit.",
  resumed: () => "Listening thread is active.",
  recommendation_ready: ({ count, top_artist }) => `${count} new leads — starting with ${top_artist}.`,
  provider_degraded: ({ provider }) => `${provider} signal weakened.`,
  provider_recovered: ({ provider }) => `${provider} signal restored.`,
  acquisition_queued: ({ artist, title }) => `Queued: ${artist} — ${title}.`,
};
```

### 3.6 Native notifications

- New Tauri plugin: `@tauri-apps/plugin-notification` (already in Tauri 2 ecosystem).
- Trigger: `track_started` event + companion enabled + `notificationsEnabled` setting + window not focused.
- Content: `"Now Playing"` title, `artist — title` body.
- Guarded by: `useSettingsStore.notificationsEnabled` toggle (new field, default `false`).

---

## 4. DB changes

None required.

---

## 5. New files

| File | Purpose |
|---|---|
| `oracle/companion/__init__.py` | package marker |
| `oracle/companion/pulse.py` | `CompanionPulse` event translator + fan-out bus |
| `oracle/api/blueprints/companion.py` | `/ws/companion` SSE endpoint |
| `desktop/renderer-app/src/hooks/useCompanionStream.ts` | SSE consumer hook |
| `desktop/renderer-app/src/features/companion/companionLines.ts` | authored line templates |
| `tests/test_companion_pulse.py` | contract tests |

---

## 6. Modified files

| File | Change |
|---|---|
| `oracle/api/__init__.py` (app factory) | register `companion` blueprint |
| `desktop/renderer-app/src/features/companion/LyraCompanion.tsx` | consume `useCompanionStream` + render event-driven lines |
| `desktop/renderer-app/src/stores/settingsStore.ts` | add `notificationsEnabled: bool` field |

---

## 7. Tests

File: `tests/test_companion_pulse.py`

| Test | Description |
|---|---|
| `test_track_started_event_emits_companion_pulse` | Player `player_track_started` → `CompanionPulse` emits `track_started` envelope |
| `test_queue_empty_emits_queue_empty_event` | `player_track_finished` with empty queue → `queue_empty` |
| `test_paused_state_change_emits_paused` | `player_state_changed` with status=paused → `paused` |
| `test_provider_degraded_emits_event` | Direct `publish_provider_event(provider, "degraded")` → `provider_degraded` |
| `test_provider_recovered_emits_event` | Direct `publish_provider_event(provider, "ok")` → `provider_recovered` |
| `test_subscribe_unsubscribe_roundtrip` | Subscribe, receive event, unsubscribe, no further delivery |

---

## 8. Execution Plan

1. Write spec ✓ (this document)
2. Implement `oracle/companion/pulse.py`
3. Register blueprint + SSE endpoint
4. Write `tests/test_companion_pulse.py` → `python -m pytest -q`
5. Implement `useCompanionStream.ts` + `companionLines.ts`
6. Update `LyraCompanion.tsx` to consume stream
7. Add `notificationsEnabled` to settingsStore + wiring (notification on track_started)
8. `npm run test:ci` + `npm run build`
9. Update docs, close Wave 11

---

## 9. Acceptance Criteria

- [ ] `python -m pytest -q` passes (≥ 201 tests)
- [ ] `/ws/companion` returns `text/event-stream`
- [ ] `LyraCompanion` displays a contextual line derived from the last backend event (not static status derivation)
- [ ] `npm run test:ci` and `npm run build` pass
- [ ] `notificationsEnabled` toggle exists in Settings (default off)
