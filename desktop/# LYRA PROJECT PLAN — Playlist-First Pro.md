# LYRA PROJECT PLAN — Playlist-First Product Path (API/Core Already Built)

Owner: Chris (snappedpoem1)  
Repo: https://github.com/snappedpoem1/lyra  
Goal: Turn Lyra from a strong API/CLI engine into a playlist-first desktop product.

---

## 0) North Star

Lyra is a **playlist-first, local-first music intelligence product**.

**The first magical loop:**
1) Type a vibe prompt  
2) Generate a playlist  
3) Play it locally  
4) Explain “why these tracks”  
5) Save as a Vibe (and optionally materialize)

Everything else exists to support that loop.

---

## 1) Current Reality (Assumed from repo intent)

- Runtime is **Core/API-first**.
- Web UI routes are not the active product surface.
- There is a working DB + embeddings + pipeline + acquisition tooling.
- There is an LLM integration path but health/state can drift if configured model != loaded model.

This plan is about turning what exists into a usable product with clear contracts.

---

## 2) Guiding Rules (Non-Negotiable)

### Safety Rules
- NEVER delete user music files automatically.
- Any rename/move/relocation must follow **PLAN → REVIEW → APPLY**.
- Every APPLY step must generate an UNDO journal that can revert the change.
- Prefer “materialize via hardlinks” when possible.

### Engineering Rules
- Freeze a v1 API contract before building UI features.
- Separate stable modules from experimental modules.
- Every major capability must have:
  - a doc page
  - a smoke test
  - a clear CLI entry or API endpoint

---

## 3) Architecture Lanes

### Core (Must be stable)
- Library scan + registry
- Metadata enrichment + merge logic
- Embeddings + vector search
- Track scoring + playlist generation
- Vibes: save/build/materialize/refresh
- History + undo journal
- Status/doctor/diagnostics

### Product (User-facing)
- Desktop UI (Electron-first preferred)
- Playback (local playback first)
- Playlist Lab (prompt → playlist → refine → save)
- Track detail (why + metadata + similarity context)

### Ops (Support)
- Acquisition queue
- External services (Docker stack)
- Repair workflows
- Export tools

### Experimental (Allowed to be unstable)
- lore / dna / scout / radio / agent / architect subsystems
- any features without tests and contract stability

---

## 4) Milestones

## Milestone A — Repo Truth + Contracts
**Goal:** The repo tells the truth and the product surface is defined.

Deliverables:
- `docs/ARCHITECTURE_OVERVIEW.md` (one-page map of lanes + data flow)
- `docs/API_CONTRACT_V1.md` (endpoints + request/response schemas)
- `docs/PRODUCT_DEFINITION.md` (playlist-first definition + UX boundaries)
- Label modules: core / ops / experimental (docs + code comments)

Acceptance:
- A new dev can read 3 docs and understand:
  - what’s stable
  - what’s experimental
  - what to run to get a playlist

---

## Milestone B — LLM Health Consistency
**Goal:** LLM-backed features are reliable and health checks match reality.

Deliverables:
- A single source of truth for LLM config (env/profile)
- A “doctor” command that reports:
  - configured model
  - loaded model (if detectable)
  - endpoint reachability
  - timeout diagnostics
- A fix path:
  - either load configured model
  - or update config to match loaded model

Acceptance:
- `/health` and `/api/status` are consistent and fast.
- Any mismatch produces a clear warning and a 2-step fix.

---

## Milestone C — Playlist MVP (Backend)
**Goal:** Lock the playlist object and explanations.

Deliverables:
- Canonical objects:
  - `PlaylistRun` (id, seed prompt, parameters, timestamp)
  - `PlaylistTrack` (track_id, rank, score, reasons[])
  - `TrackReason` (type, evidence, weight)
- Endpoints (names can vary, contract must be stable):
  - Generate playlist from prompt/seed
  - Explain a track’s inclusion
  - Save playlist as Vibe
  - List recent playlist runs

Acceptance:
- Given a prompt, Lyra can generate a playlist and explain itself in structured data.
- A playlist run can be saved and reloaded.

---

## Milestone D — Product MVP (Desktop UI)
**Goal:** A real person can use Lyra without reading your brain.

Screens:
1) Prompt/Search
2) Playlist Results (ordered list, playable)
3) Track Detail Drawer (why + metadata + links)
4) Save as Vibe
5) History (playlist runs + undo journal visibility)

Acceptance:
- A user can create and play a playlist from a prompt in under 60 seconds.
- “Why this track” is visible and understandable.
- Saving as a Vibe works.

---

## Milestone E — Vibes as the Hero
**Goal:** Vibes are the primary saved artifact.

Deliverables:
- Vibe library screen
- Vibe build/materialize/refresh controls (with safety constraints)
- Vibe “route map”:
  - stats (tempo spread, mood spread, genres)
  - top reasons summary

Acceptance:
- Vibes feel like living “worlds” you can revisit and evolve.

---

## Milestone F — Polish Layer (After MVP is done)
Optional, post-MVP:
- MilkDrop-like visualizer
- constellation graph (track/artist similarity)
- chaos modes (contrast injection)
- rediscovery mode

Acceptance:
- Adds delight without harming reliability.

---

## 5) Work Breakdown (Next 10 Tasks)

1. Add docs folder structure:
   - `docs/ARCHITECTURE_OVERVIEW.md`
   - `docs/API_CONTRACT_V1.md`
   - `docs/PRODUCT_DEFINITION.md`

2. Create `docs/MODULE_CLASSIFICATION.md` listing:
   - core modules
   - ops modules
   - experimental modules

3. Implement a single “doctor” command output that includes:
   - python version
   - DB paths and writable status
   - chroma presence
   - service reachability
   - LLM config vs runtime warning

4. Freeze playlist schema objects + serialization.

5. Build/confirm playlist generation endpoint.

6. Build/confirm explain endpoint.

7. Build “save as vibe” endpoint and “list vibes”.

8. Smoke tests:
   - scan -> embeddings -> search -> generate playlist -> explain -> save vibe

9. Create UI shell (Electron):
   - call API endpoints
   - render playlist
   - play local files

10. Create the “Playlist Lab” MVP screen.

---

## 6) Definition of Done (v1)
Lyra v1 is done when:
- Playlist generation feels intentional (not random)
- Explanations are clear and structured
- Vibes can be saved and revisited
- UI is stable and fast
- Safety workflow is enforced for file operations
- Doctor report makes debugging straightforward

---

## 7) Notes on Scope Control
- Acquisition stays a supporting tool unless it directly serves “complete the library for better playlists.”
- Experimental modules do not block MVP.
- No “big settings cathedral” until the core loop is loved.