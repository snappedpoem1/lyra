# Lyra Project State

Last audited: March 9, 2026

## Canonical Runtime Truth

Lyra's canonical runtime is:

- Tauri 2 desktop shell
- SvelteKit SPA renderer
- Rust application core in `crates/lyra-core`
- Rust-owned SQLite local store

Python is not part of canonical startup, playback, queue, library, or normal app operation.
Legacy Python and oracle code remain in-repo as migration-source logic.

## Product Reality

Lyra is not blocked on becoming a native desktop app.
The active challenge is product identity depth: making the canonical app feel like Lyra instead of a competent local player.

Current product framing:

- Lyra is a vibe-to-journey intelligence and discovery system with native playback
- the composer is the front door
- playback, acquisition, provenance, and provider plumbing are support infrastructure

## Implemented Now

- Python-free canonical runtime boot path
- Rust-owned playback, queue, playlists, settings, provider config records, and local DB state
- acquisition workflow and horizon intelligence infrastructure
- enrichment provenance and confidence surfaces
- related-artist and graph scaffolding
- first real composer slice in the canonical runtime:
  - typed `PlaylistIntent`
  - local/cloud LLM provider abstraction
  - shared Rust `LlmClient` for OpenAI-compatible calls in playlist narration
  - explicit provider selection and fallback mode in settings
  - deterministic retrieval, reranking, and sequencing in Rust
  - first-class composer action routing: draft, bridge, discovery, explain, steer
  - typed Lyra framing output for posture, detail depth, confidence phrasing, fallback honesty, route comparison, and next nudges
  - presence-aware framing for protect-the-vibe behavior, sideways temptation, and co-curator guidance
  - visible playlist phases and bridge/discovery route surfaces in the Svelte UI
  - steering controls for obviousness, adventurousness, contrast, warmth/nocturnal bias, and explanation depth
  - companion-style UI framing that renders Lyra guidance instead of raw engine output alone
  - role-aware response behavior for recommender, coach, copilot, and oracle modes
  - persisted taste-memory layer with session posture, rolling remembered preferences, route-choice history, and recency/confidence notes
  - track-level reason payloads
  - saved reason payload persistence in `playlist_track_reasons`
  - weird-prompt evaluation coverage for action classification and deterministic fallback honesty
  - canonical persona docs in `docs/LYRA_VOICE_AND_PERSONA.md` and `docs/LYRA_BEHAVIOR_EXAMPLES.md`
  - adjacency-aware bridge and discovery variants with typed safe / interesting / dangerous / direct bridge / scenic / contrast logic
  - bridge-step adjacency signals that name what each step preserves, changes, and leads toward
  - partial legacy semantic ports from `oracle/arc.py` and `oracle/explain.py`:
    - adjacent-swap transition optimization inside sequenced routes
    - dimension-distinctiveness and taste-alignment evidence in track reasons
    - stronger novelty/deep-cut phrasing grounded in local play history
  - graph-backed adjacency pressure from local artist connections, co-play evidence, and shared-genre fallbacks
  - act-template-shaped playlist phases inspired by legacy `playlust.py` templates instead of one generic four-step contour
  - prompt-pressure phase shaping ported from legacy mood/vibe logic so prompts can now bias arc energy, warmth, space, and detour appetite instead of only changing copy
  - stronger local deep-cut / anti-canon pressure inside route scoring so `less obvious`, `not the canon`, `rougher`, and `more human` can materially move selection behavior
  - partial scene-targeting lift from legacy `oracle/scout.py` so scene-exit prompts now bias route worlds through adjacent and contrast scene families rather than only generic novelty
  - explicit route feedback capture from the Cassette route comparison surface so Lyra can remember accepted vs rejected lanes
  - provider-authored narrative constrained behind a Lyra contract instead of freeform assistant narration
  - Groq/OpenRouter failover for playlist narration extracted from `playlists.rs` inline HTTP wiring into shared Rust client code
  - provider-assisted intent parsing sanitized back to Lyra's allowed roles, energies, novelty/aggression enums, explicit-entity limits, and fallback honesty
  - first-class scene-exit handling for prompts such as `same pulse, different world`, `leave this genre, keep this wound`, and `stay in the ache, lose the gloss`
  - Lyra-read surface with bounded, evidence-aware pressure summaries instead of decorative taste copy
  - route audition teasers in the Cassette workspace so safe / interesting / dangerous lanes can be felt, not only read
  - saved playlist detail now retains structured why/transition/evidence/explicit-vs-inferred payloads instead of flattening everything to one reason string
  - persisted composer-run history so recent Lyra routes can be reopened with their full structured response payload instead of evaporating when the live result is replaced
  - persistent composer diagnostics in SQLite plus a right-rail Cassette surface for recent compose success/failure events during test deployment
  - first canonical Spotify evidence and gap surface in the Lyra workspace:
    - counts for imported Spotify history/library/features where available
    - top Spotify worlds that still have missing owned-library coverage
    - direct queueing of missing Spotify tracks into acquisition from the workspace
    - prompt seeding for missing-world recovery instead of treating Spotify only as a hidden queue seed
  - Spotify-derived missing-world pressure now reaches the route engine:
    - discovery flavor choice can shift toward interesting or dangerous when scene-exit prompts touch worlds Spotify history says mattered
    - novelty and anti-canon appetite can rise when the owned library still undercovers those remembered worlds
    - Lyra-read and route rationale can now admit when Spotify memory is influencing the route
  - Discover now carries missing-world recovery and route-handoff behavior instead of only flat recommendation loading:
    - Spotify-derived missing worlds and top artists surface directly in Discover
    - Discover recommendation cards now offer Lyra route handoff and missing-world recovery actions
    - recent discovery rows can jump directly into route prompts instead of only artist detail
  - Acquisition now exposes missing-world recovery as a first-class queue-building lane:
    - Spotify gap summaries appear alongside queue and preflight work
    - top missing artists can be handed directly into Lyra recovery prompts
    - missing tracks can be batch-queued from the acquisition workspace instead of only from the composer shell
  - Artist related-artist surfaces now carry preserve/change/risk language instead of only connection bars and percentages
  - Artist and Library now retain more Lyra behavior outside the composer:
    - Artist top tracks can show `Why` and `Proof` directly from the route shell
    - Artist pages now offer direct Lyra route chips and bridge handoff instead of only play/queue controls
    - Library search now has an excavation panel that can hand matching rows directly into route prompts instead of stopping at filtering
    - Library rows can now open Lyra explanations directly instead of forcing all reasoning through the main composer page
  - Discover recommendations now carry composer-grade structured evidence payloads:
    - `RecommendationResult` carries `provider`, `whyThisTrack`, and a structured `evidence: Vec<EvidenceItem>` alongside `score`
    - `ExplainPayload` upgraded from flat `reasons: Vec<String>` to `whyThisTrack`, `evidenceItems`, `explicitFromPrompt`, `inferredByLyra`
    - `RecommendationBroker` now runs three lanes: `local/taste`, `local/deep_cut`, and `scout/bridge` (cross-genre bridge from local library using ported genre adjacency map)
    - `graph/co_play` lane pulls artist-connection evidence from the local artist graph
    - Discover cards show a provider badge per recommendation and inline evidence chips; the Why? panel now renders structured evidence rows instead of a flat reason list
  - Cassette-branded shell framing with a more prototype-faithful Lyra workspace for intelligence evaluation
  - Cassette now owns installer/window/app-shell branding while Lyra remains the intelligence layer inside it
  - Cassette-branded packaged artifacts now build successfully as NSIS and MSI bundles from the canonical Tauri app

## Still Missing

The current composer slice is foundational, not complete.
Major gaps remain:

- stronger prompt-to-discovery coverage outside the composer workspace
- deeper bridge-track and adjacency reasoning from real library evidence beyond improved local scoring, transition optimization, and typed route logic — scout bridge lane now active in Discover but ListenBrainz weather and full multi-provider fusion remain Python-only
- richer explanation coverage across saved playlists and recommendation surfaces — Discover now has composer-grade evidence depth but saved playlist detail surfaces still lag
- deeper scene-exit and adjacency language across artist/discovery surfaces outside the main composer workspace
- Discover still lags the composer and Artist route surfaces in typed adjacency language and richer route comparison
- stronger local-LLM and cloud-LLM provider breadth and credential ergonomics
- broader acceptance/rejection learning beyond the current route-comparison feedback capture
- broader migration of legacy semantic search, graph, and explainability behavior into Rust beyond the current arc/explain partial port
- broader use of Spotify-derived taste and gap evidence across Artist and deeper Search memory, plus deeper feedback back into memory, instead of only the main Lyra workspace, Discover, Acquisition, and current route engine hooks
- deeper provider compliance enforcement for non-narrative outputs beyond the now-constrained intent parser
- clean-machine installer proof and long-session packaged validation for the new Cassette identity

## Current Priority Order

1. `G-063` Composer and playlist intelligence depth
2. `G-064` Discovery graph and bridge depth
3. `G-061` Explainability and provenance breadth
4. `G-060` Remaining acquisition runtime risk
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

This order is deliberate:

- composer and discovery are product identity
- explainability must stay close behind them
- acquisition remains important but is infrastructure
- package polish is a release gate, not the mission

## Configuration And Credential Reality

Provider and API configuration already exists in the repo and local environment.
This is not a blank configuration project.

Grounded facts:

- Rust persists provider config records in SQLite
- provider capability metadata already exists in Rust
- provider validation hooks already exist in Rust
- OS keyring support already exists in Rust
- the new composer pipeline reuses this provider config path for local/cloud LLM selection

Do not expose secrets in docs, logs, or summaries.
