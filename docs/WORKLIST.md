# Worklist

Last updated: March 9, 2026

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

### Whole-Dream Reconciliation

Goal: turn the product dream into a grounded, checkable build program instead of scattered ambition.

- [x] Create a repo-backed whole-product checklist that distinguishes canonical reality from legacy debt and spec-backed ambition
- [x] Promote Spotify export/history/library from side input to visible product evidence in the Cassette workspace
- [x] Feed Spotify-derived missing-world and taste pressure into Lyra route generation instead of leaving it as summary and acquisition data only
- [x] Carry Spotify missing-world recovery and route handoff into Discover and Acquisition so the intelligence stops peaking only inside the main Lyra workspace
- [x] Push Lyra explanation and route handoff into Artist and Library so non-composer surfaces stop collapsing back into plain catalog controls
- [ ] Promote Scout, search-as-excavation, and broader route language deeper into Discover and Artist surfaces
- [ ] Close the next highest-value product-defining boxes from `docs/WHOLE_DREAM_CHECKLIST.md`

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
- [x] Replace the light steer-memory hook with a persisted session-plus-rolling taste-memory layer
- [x] Push persona rules deeper into provider-authored narratives and route narration surfaces
- [x] Extract playlist narration LLM transport/failover into a shared Rust client so composer-facing playlist flows stop duplicating inline HTTP logic
- [x] Learn from explicit accepted/rejected route choices instead of only prompt and steer pressure
- [x] Constrain provider-assisted intent parsing behind the same Lyra contract boundaries used for narrative output
- [x] Make scene exits first-class in the composer instead of treating them as generic discovery copy
- [x] Add a Lyra-read surface and route-audition teaser mode that expose pressure, route feel, and fallback honesty directly in Cassette
- [x] Persist recent composer runs so Lyra routes can be reopened with full structured reasoning from the shell
- [x] Surface Spotify history/library gap evidence in the main Lyra workspace so missing-world recovery is visible during composition
- [ ] Continue the legacy semantic port beyond the current `oracle/arc.py`, `oracle/explain.py`, `oracle/scout.py`, mood-pressure shaping, graph-context lift, and playlust-style act shaping so adjacency relies on richer semantic/graph evidence, not only local scoring and transition optimization

### G-064 Discovery Graph And Bridge Depth

Goal: make adjacency exploration feel like a core Lyra capability.

- [x] Turn bridge prompts into first-class composer actions
- [x] Add typed safe / interesting / dangerous discovery routes plus direct / scenic / contrast bridge variants
- [x] Add bridge-step preserve/change/adjacency explanation scaffolding that stays grounded in route logic
- [x] Pull graph-backed artist adjacency into composer route scoring and evidence where local connections exist
- [ ] Expand related-artist and graph surfaces into the same adjacency language used by the composer
- [x] Bring graph evidence and route memory into the composer and discovery surfaces together
- [x] Bias scene-exit routes toward adjacent and contrast scene families instead of treating every detour as generic novelty
- [ ] Carry the new scene-exit / route-audition language deeper into artist and discovery pages outside the composer workspace

### G-061 Explainability And Provenance Breadth

Goal: keep the intelligence layer legible everywhere it matters.

- [x] Carry the new reason payload model into saved playlists and their revisit surface
- [x] Expose inferred-vs-explicit reasoning consistently in live and saved playlist detail
- [x] Carry the same persisted reason payload model into recommendation detail and non-composer discovery surfaces — Discover now has EvidenceItem + whyThisTrack + inferredByLyra at composer payload depth
- [ ] Replace the current Library excavation handoff layer with a deeper canonical search surface instead of leaving excavation partially embedded inside catalog UI
- [x] Keep degraded provider states explicit in composer and explanation surfaces
- [x] Persist composer diagnostics so deploy-time failures can be inspected from inside Cassette during first-session testing

### G-060 Remaining Acquisition Runtime Risk

Goal: preserve trust in the support infrastructure without letting it dominate roadmap identity.

- [ ] Replace the remaining Python waterfall executor
- [ ] Finish external metadata-validator parity

### G-062 Curation Workflows

- [ ] Restore duplicate review, keeper selection, cleanup preview, and undo depth

### G-065 Packaged Desktop Confidence

- [x] Build a Cassette-branded packaged installer after the current intelligence pass
- [ ] Run clean-machine installer and long-session confidence proof after the packaged build
