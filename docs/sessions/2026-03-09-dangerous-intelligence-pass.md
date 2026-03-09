# Session Log - S-20260309-02

**Date:** 2026-03-09
**Goal:** Deepen semantic intelligence, tastemaker adjacency, feedback-aware memory, scene exits, route audition, broader explainability, provider parsing obedience, and packaged installer readiness
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

What was the state of the project at the start of this session?
Reference `docs/PROJECT_STATE.md` if relevant.

The canonical Rust/Tauri/Svelte composer already had:

- typed playlist / bridge / discovery / steer / explain actions
- taste-memory persistence and explicit route feedback capture
- graph-backed adjacency pressure and partial legacy arc / explain / playlust ports
- a Cassette-shaped testing shell with route comparison and right-rail explanation

The main honest gaps were still:

- provider parsing could drift outside Lyra's contract
- scene exits were heuristic rather than first-class
- saved explanation payloads still flattened at the playlist-detail boundary
- route audition and Lyra-read surfaces were missing
- app and installer branding still presented Lyra as the outer shell instead of Cassette

---

## Work Done

Bullet list of completed work:

- [x] Strengthened provider-assisted intent parsing with canonical sanitization for roles, energies, novelty, discovery aggressiveness, explanation depth, transition style, and explicit-entity bounds
- [x] Made scene exits first-class inside discovery prompts and route framing
- [x] Added bounded route-memory pressure to route selection and primary-lane recommendation
- [x] Added `primary_flavor` and `scene_exit` to discovery results so Cassette can show the truest lane instead of highlighting everything
- [x] Added a typed Lyra-read surface with evidence-aware pressure summaries and confidence notes
- [x] Added route audition teasers and play/queue actions to the Cassette composer workspace
- [x] Expanded saved-playlist explainability so structured reason payloads, phase labels, evidence, and inferred-vs-explicit reasoning survive revisit
- [x] Switched packaged app/window branding to Cassette in Tauri config while keeping Lyra as the intelligence layer
- [x] Added regression tests for scene exits, route-memory lane bias, and provider-parse obedience
- [x] Built Cassette-branded NSIS and MSI installers from the canonical Tauri app
- [x] Ported mood-pressure shaping from legacy mood/vibe logic so prompt wording can bias per-phase energy, warmth, space, and detour appetite
- [x] Ported a bounded scout-style scene-family target layer so scene exits bias toward adjacent or contrast worlds instead of generic novelty
- [x] Added persistent composer diagnostics storage plus a Cassette right-rail diagnostics surface for first-session deploy debugging
- [x] Added stronger deep-cut / anti-canon route pressure so `less obvious`, `not the canon`, `rougher`, and `more human` materially affect selection
- [x] Added persistent composer-run history so recent Lyra routes can be reopened with their full structured response and reasoning payload

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | local changes, no commit yet |

---

## Key Files Changed

- `crates/lyra-core/src/intelligence.rs` - provider-parse sanitization, scene exits, primary discovery lane selection, Lyra-read surface, challenge behavior, and new tests
- `crates/lyra-core/src/commands.rs` - typed Lyra-read, saved playlist reason-record, and discovery-route fields
- `crates/lyra-core/src/playlists.rs` - persisted structured reason payload fetch for saved playlists
- `desktop/renderer-app/src/routes/playlists/+page.svelte` - route audition UI, Lyra-read panel, and corrected route-card highlighting
- `desktop/renderer-app/src/routes/playlists/[id]/+page.svelte` - saved reason/evidence/inferred-vs-explicit rendering
- `crates/lyra-core/src/composer_diagnostics.rs` - persistent compose success/failure event logging
- `crates/lyra-core/src/composer_history.rs` - recent Lyra route persistence and reopen support
- `desktop/renderer-app/src-tauri/tauri.conf.json` - Cassette product/window/bundle identity
- `docs/PROJECT_STATE.md` - capability truth update
- `docs/WORKLIST.md` - next-work reprioritization
- `docs/MISSING_FEATURES_REGISTRY.md` - gap matrix update
- `docs/LYRA_INTELLIGENCE_CONTRACT.md` - provider parsing, scene-exit, and UI-surface contract additions

---

## Result

Did the session accomplish its goal? What is now true that was not true before?

Lyra now has a stronger canonical intelligence pass in the places that matter most for first-session product truth:

- provider-assisted parsing is constrained instead of trusted raw
- scene exits are visible as first-class discovery behavior
- route memory can bias the recommended lane without pretending deep certainty
- saved playlists retain more of their actual why/transition/evidence payload
- the Cassette shell can now show Lyra's read and let the user audition route lanes quickly
- prompt wording now has more real force over phase shape and scene targeting instead of mostly affecting labels
- first deploy/test sessions can inspect recent compose failures from inside Cassette instead of depending only on terminal logs
- recent Lyra work now survives the live composer moment and can be reopened from the Cassette shell
- the packaged app identity now presents Cassette as the shell and Lyra as the intelligence within it
- Cassette now produces packaged installer artifacts again after the behavior pass

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [ ] `docs/SESSION_INDEX.md` row added
- [x] `docs/PROJECT_STATE.md` updated
- [x] `docs/WORKLIST.md` updated
- [x] `docs/MISSING_FEATURES_REGISTRY.md` updated
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `cargo test -p lyra-core`
- [x] Installer build passes: `npm run tauri:build`

---

## Next Action

What is the single most important thing to do next?

Run clean-machine validation on the new Cassette installer, then carry the new scene-exit / route-audition / explainability language into artist and discovery surfaces outside the main composer workspace.

