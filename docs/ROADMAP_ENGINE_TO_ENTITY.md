# Lyra: Engine to Entity - Unified Master Plan

Last updated: March 6, 2026

This file is the single forward-plan authority for Lyra.
It merges the original Engine-to-Entity vision with the Unified App Cutover execution track.

## 1) Mission Lock

Lyra is a local-first music entity: one app entrypoint for playback, library, queue, oracle actions, and acquisition control surfaces.

Core priority:

- Listening experience first.
- Backend expansion only when it ships visible user value in the same or next phase.

## 2) Decision Lock

1. Tauri is the only supported desktop host path.
2. Backend player is canonical playback authority.
3. Browser `HTMLAudio` is non-canonical runtime behavior.
4. Unified modular workspace shell is the active UI runtime.
5. Docker is optional acquisition support, not required for daily local playback.
6. Ambient oracle behavior is default when oracle action layer is enabled.

## 3) Current Accomplishment

### Host and runtime

- Tauri shell scaffold exists and builds.
- Desktop boot scripts route to Tauri-first flow.
- Tray/media controls route to backend player commands.

### Canonical player backend

- `oracle/player/*` domain implemented with persisted `player_state` and `player_queue`.
- Canonical API contract implemented:
  - `GET /api/player/state`
  - `GET /api/player/queue`
  - `POST /api/player/play`
  - `POST /api/player/pause`
  - `POST /api/player/seek`
  - `POST /api/player/next`
  - `POST /api/player/previous`
  - `POST /api/player/queue/add`
  - `POST /api/player/queue/reorder`
  - `POST /api/player/mode`
- `/ws/player` event stream implemented as SSE.
- `/api/playback/record` kept as compatibility-only, non-canonical path.

### Unified frontend shell

- Active runtime replaced with one modular workspace shell:
  - Library pane
  - Now Playing pane
  - Queue pane
  - Collapsible Oracle pane
- Player state is hydrated from backend snapshots plus SSE stream updates.

### Oracle action contract

- `POST /api/oracle/chat`
- `POST /api/oracle/action/execute`
- `GET /api/oracle/context`

### Recommendation orchestration

- `POST /api/recommendations/oracle` broker implemented.
- Broker fuses local radio, Last.fm similar-track signals, and ListenBrainz community popularity.
- Unified Oracle surface now exposes:
  - novelty bands
  - provider weighting
  - explicit chaos presets
  - explainable recommendation provenance
  - acquisition radar leads

## 4) Open Gaps

1. Native audio production validation (`miniaudio`) on real devices/long sessions.
2. Packaged sidecar certainty (`lyra_backend.exe`) on clean machine installer.
3. Oracle action breadth beyond current contract stubs.
4. Recommendation outcome logging and one-click acquisition actions.
5. Transition DJ layer (future phase).

## 5) Phase Plan

### Phase A - Daily Driver Parity (current)

Gate:
- Full listening sessions in Lyra with no CLI dependency.

Deliverables:
- Sidecar packaging hardening.
- Device/soak validation for native audio path.
- Startup/recovery reliability.

### Phase B - Surface Completion

Gate:
- Existing intelligence is fully visible in-player.

Deliverables:
- Now Playing intelligence depth.
- Vibes and Playlust controls wired in UI.
- Discover/Deep Cut UX polish.

### Phase C - Oracle Action Reliability

Gate:
- Oracle responses reliably mutate playback state and queue.

Deliverables:
- Action routing hardening.
- Ambient default behavior polish.
- Strong local context grounding from outcomes.

### Phase D - Transition DJ Layer

Gate:
- Intentional audible transitions without harming gaming performance.

## 6) Non-Negotiables

- No regressions to one-launch unified app behavior.
- No backend side quests without listening UX impact.
- No mandatory Docker dependency for daily playback.
- No forced oracle chatter while silent mode is selected.

## 7) North Star

Revelations per week:
recommended tracks that are both saved and replayed within 7 days.
