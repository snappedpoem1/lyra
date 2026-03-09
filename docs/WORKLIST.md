# Worklist

Last updated: March 8, 2026

## Current State

- Rust, Tauri, and SvelteKit are the active runtime path.
- The canonical composer contract now has a first real implementation slice in code.
- Acquisition, provenance, and horizon infrastructure remain valuable, but they are not Lyra's identity.

## Execution Rule

Prioritize the work that makes Lyra feel like a music intelligence system:

1. discovery
2. vibe-to-journey playlist authorship
3. explainability
4. taste steering
5. bridge and adjacency exploration

Do not let playback polish, queue polish, or generic app-shell work displace those lanes.

## Priority Order

1. `G-063` Composer and playlist intelligence depth
2. `G-064` Discovery graph and bridge depth
3. `G-061` Explainability and provenance breadth
4. `G-060` Remaining acquisition runtime risk
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

## Active Lane

### G-063 Composer And Playlist Intelligence

Goal: make the Lyra composer the real front door to the product.

- [x] Add typed `PlaylistIntent`
- [x] Add local/cloud LLM provider abstraction with explicit fallback reporting
- [x] Parse freeform prompts into structured intent
- [x] Retrieve candidates from local data and rerank/sequence deterministically
- [x] Surface parsed intent, provider mode, phases, and track-level why in the UI
- [x] Persist reason payloads when saving composed playlists
- [x] Deepen prompt coverage beyond playlist drafting into recommendation, bridge, discovery, steering, and explanation flows
- [x] Add richer iterative refinement and playlist steering loops
- [x] Add weird-prompt evaluation coverage for action classification and deterministic fallback honesty
- [x] Operationalize voice/persona as typed composer behavior instead of decorative copy
- [x] Add a light taste-memory hook for recurring steer posture
- [ ] Port stronger semantic retrieval behavior from legacy `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, and `oracle/arc.py`
- [ ] Push persona rules deeper into provider-authored narratives and saved-playlist explanation surfaces

### G-064 Discovery Graph And Bridge Depth

Goal: make adjacency exploration feel like a core Lyra capability.

- [x] Turn bridge prompts into first-class composer actions
- [ ] Expand related-artist results into explained adjacency paths
- [ ] Bring graph and bridge evidence into the composer and discovery surfaces together

### G-061 Explainability And Provenance Breadth

Goal: keep the intelligence layer legible everywhere it matters.

- [ ] Carry the new reason payload model into saved playlists, discovery, and recommendation surfaces more broadly
- [ ] Expose inferred-vs-explicit reasoning consistently
- [x] Keep degraded provider states explicit in composer and explanation surfaces

### G-060 Remaining Acquisition Runtime Risk

Goal: preserve trust in the support infrastructure without letting it dominate roadmap identity.

- [ ] Replace the remaining Python waterfall executor
- [ ] Finish external metadata-validator parity

### G-062 Curation Workflows

- [ ] Restore duplicate review, keeper selection, cleanup preview, and undo depth

### G-065 Packaged Desktop Confidence

- [ ] Validate packaged installer and long-session confidence after identity-defining lanes are stronger
