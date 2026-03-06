# Ecosystem Pivot Research - Lyra Oracle

Date: 2026-03-05
Session: S-20260305-06
Scope: external due diligence + internal architecture fit check

## 1) What Lyra does now (confirmed from repo docs)

- Backend: Python 3.12 + Flask API + APScheduler
- Stores: SQLite (`lyra_registry.db`) + Chroma (`chroma_storage/`)
- UI: React 18 + Vite renderer (`desktop/renderer-app`)
- Library state: 2,454 tracks indexed/scored/embedded
- Emotional model: 10 dimensions (energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia)
- Acquisition waterfall: Qobuz -> Streamrip -> Slskd -> Real-Debrid -> SpotDL
- Current known gaps: playback proof session, graph richness depth, streamrip runtime install, spotify export scope decision

## 2) Inline findings log (what exists already, and whether it beats custom build)

### A. Acquisition and ingestion stack

1. Streamrip upstream is active (`v2.1.0`, Jun 4 2025), but explicitly notes Spotify API changes (Nov 2024) broke Spotify use inside streamrip itself.
   - Impact: keep Lyra tier-2 streamrip for Qobuz/Tidal/Deezer workflows, but do not bet roadmap on Spotify-through-streamrip.
2. slskd is active (`v0.24.5`, Mar 1 2026) with documented API.
   - Impact: strong keep; this is a stable integration beam.
3. rdt-client is active (`v2.0.100`, Feb 9 2026) and broad on torrent backends.
   - Impact: keep; focus on queue policy and validation layers rather than replacing core transport.
4. Lidarr remains active and purpose-fit for monitoring/acquisition orchestration.
   - Impact: keep as optional companion service; do not clone Lidarr behavior in Lyra.

Verdict: keep current waterfall shape, but promote "adapter quality" over rewriting downloader logic.

### B. Metadata, tagging, and library intelligence

1. beets remains heavily active (14k+ stars, Jan 2026 release, deep plugin ecosystem).
   - Impact: treat beets as metadata normalization engine, not a competitor.
2. Last.fm + ListenBrainz ecosystems still provide viable graph/recommendation signals.
   - Impact: expand dual-source graph strategy instead of single-source dependency.

Verdict: build around existing metadata ecosystems; Lyra value is multi-source fusion + reasoning.

### C. Discovery and recommendation ecosystems (already solved parts)

1. Lidify (2k+ stars) already does Last.fm -> Lidarr recommendation queueing.
2. Sonobarr already does Last.fm history-driven recommendation + Lidarr queueing.
3. DiscoveryLastFM exists, but reports Spotify API restrictions reduced utility for that approach.
4. ListenBrainz exposes recommendation surfaces (User CF, Artist CF, recordings-by-tag, exploration mode, fresh releases).

Verdict: the raw recommendation primitives are not novel anymore; Lyra should not reinvent baseline recommenders. Lyra should orchestrate and rank across them.

### D. Spotify API risk surface (important)

1. Spotify developer update (Nov 27, 2024): development-mode access is constrained and extension is required for broader functionality.
2. Spotify reference pages currently mark key endpoints as deprecated, including recommendations and audio-features pages.

Verdict: any architecture depending on open Spotify recommendation/audio-feature endpoints is now policy-risky. Lyra should treat Spotify as one signal source, not the backbone.

### E. Vector/search layer

1. Qdrant is highly active and explicit about hybrid search + integrations + FastEmbed.
2. Chroma remains easy for Python-first local prototyping.

Verdict: keep Chroma while dataset is moderate; stage a migration path to Qdrant only if hybrid retrieval quality or scaling pain shows up.

### F. Audio representation models

1. CLAP remains practical and already integrated in Lyra.
2. Newer/open alternatives exist: MuQ, MusicFM, MERT (large adoption signal on model downloads).

Verdict: do not swap core model immediately; run a benchmark harness first (retrieval quality, speed, VRAM/RAM, cold start).

### G. UI and the "8-bit face" assistant concept

1. Open-LLM-VTuber demonstrates mature desktop avatar + voice + Live2D patterns.
2. Witsy demonstrates desktop AI assistant + MCP client + multi-agent workflows.
3. Clippy.js shows low-friction nostalgic on-screen assistant patterns.

Verdict: yes, the corner companion is technically feasible now without massive custom R&D. Build as optional UI shell around existing agent routing, not as a new core backend.

### H. Community signal from Reddit/self-hosting threads

1. Real users still ask for mood-based and discovery-first recommendation stacks.
2. Common answers cluster around Last.fm, ListenBrainz plugins, and lightweight mood tools.

Verdict: demand exists, but most stacks are fragmented. Lyra's opportunity is unified orchestration + explainability.

## 3) Pivot point identified

Pivot statement:

- Lyra should become a "music intelligence orchestrator" that composes proven systems (acquisition, tagging, scrobble ecosystems, recommendation feeds) into one explainable controlled-surprise engine.
- The unique moat is not "another downloader" or "another Last.fm recommender". The moat is cross-system fusion, emotional topology, and intent-aware navigation (your chaos dial vision).

## 4) Keep / trim / add recommendations

Keep:

- Waterfall architecture with hard guardrails
- Local-first SQLite + vector retrieval approach
- 10-dimension emotional model
- Desktop-first workflow

Trim or de-prioritize:

- Any roadmap that depends on deprecated/restricted Spotify endpoints
- Re-implementing functionality that Lidarr/slskd/rdt-client already cover well
- UI work that is disconnected from recommendation explainability

Add next:

1. Build a provider-agnostic recommendation broker:
   - Inputs: local graph, Last.fm, ListenBrainz, internal embedding neighbors
   - Output: normalized candidate pool + confidence/explanation metadata
2. Build a benchmark harness for embedding model swaps (CLAP vs MuQ/MusicFM/MERT)
3. Add "Companion Layer" MVP in renderer (toggleable corner character):
   - status reactions (queue health, acquisition, discovery events)
   - contextual prompts tied to real recommendation explanations
4. Add architecture boundaries for optional external orchestrators (Lidarr/Navidrome/Jellyfin interop)

## 5) Yes/No decision questions (for scope lock before implementation)

### Core identity

1. Should Lyra explicitly position itself as an orchestrator instead of a monolithic all-in-one stack?
2. Should we stop building duplicate downloader behavior when a mature service already exists?
3. Should every new feature be rejected unless it strengthens controlled-surprise quality?
4. Should explainability be required for every recommendation surfaced in UI?
5. Should we treat Spotify as auxiliary instead of primary going forward?

### Recommendation engine

6. Should we add a recommendation broker layer that merges Last.fm, ListenBrainz, local graph, and embedding signals?
7. Should each candidate carry a machine-readable "why this" payload?
8. Should we add provider weighting controls (per-source trust sliders)?
9. Should we add novelty bands (safe, stretch, chaos) as first-class API parameters?
10. Should we persist recommendation outcomes (accepted/skipped/replayed) as training feedback?

### Data and graph

11. Should graph enrichment be prioritized over new UI chrome for the next cycle?
12. Should we expand edge types beyond similarity + dimension affinity before adding more recommendation modes?
13. Should we import ListenBrainz recommendation signals directly into graph edges?
14. Should we add time-of-day and session-context edges for better "2am vs noon" behavior?
15. Should we build genre-hop distance explicitly for chaos dial control?

### Embeddings and retrieval

16. Should CLAP stay default until benchmark evidence says otherwise?
17. Should we create a pluggable embedding provider interface now?
18. Should we benchmark MuQ, MusicFM, and MERT on a fixed local eval set?
19. Should hybrid search (vector + symbolic constraints) be mandatory for recommendation ranking?
20. Should we defer vector DB migration unless latency/quality regression is measured?

### Acquisition and infrastructure

21. Should streamrip be treated as best-effort tier only (no Spotify dependency assumptions)?
22. Should we formalize health scoring per acquisition tier and expose it to UI?
23. Should failed acquisitions auto-route to next tier with reason codes stored?
24. Should Docker service state gate recommendation confidence (for freshness-sensitive flows)?
25. Should we keep Lidarr as optional companion instead of trying to absorb its whole domain?

### API and backend architecture

26. Should we create a strict provider adapter contract for all external recommendation/data sources?
27. Should we require contract tests for every adapter before enabling in production profile?
28. Should we add idempotent event logging for recommendation decisions and user feedback?
29. Should we expose recommendation provenance in API responses by default?
30. Should we version recommendation payload schemas before adding new providers?

### UI and experience

31. Should the next UI iteration prioritize "insight moments" over more panels/routes?
32. Should each recommendation card show rationale in plain language plus technical trace?
33. Should the chaos dial become a persistent global control in transport or top bar?
34. Should we make fixture mode harder to accidentally enable in normal usage?
35. Should recommendation failure states be visible instead of silently degraded?

### Companion / 8-bit face concept

36. Should we build a toggleable corner companion as an optional feature flag?
37. Should companion behavior be event-driven from existing agent/router signals?
38. Should companion output be mostly nonverbal/status-first to avoid novelty fatigue?
39. Should we support both pixel-art and Live2D style skins behind same interface?
40. Should we keep companion logic client-side so backend complexity does not spike?

### Desktop and platform

41. Should we continue Electron-first or run a Tauri feasibility spike?
42. Should we require performance budgets (CPU/RAM) for every new desktop feature?
43. Should we add a low-resource mode that disables heavy animations/visualizers/companion?
44. Should we expose CLAP runtime status directly in renderer diagnostics permanently?
45. Should we add startup profile presets (Discovery, Acquisition, Lightweight)?

### Docker and ops

46. Should docker-compose include optional profiles for minimal vs full-stack services?
47. Should we add one-click preflight that validates all external service/API credentials before run?
48. Should we export health + queue metrics to a single diagnostics endpoint for UI and scripts?
49. Should we auto-pause expensive background jobs when system resource pressure is high?
50. Should we maintain a hard "no destructive migration without prompt" policy in CLI commands?

### Product strategy

51. Should we ship an integration-first milestone before any major new algorithm work?
52. Should we define one north-star metric (successful revelations per week) and instrument for it?
53. Should we formalize "done" for discovery features as acceptance + replay outcomes, not just API success?
54. Should we keep a rolling ecosystem watchlist for upstream breaks (Spotify policy, API deprecations, fork health)?
55. Should we lock the next cycle to 3 high-impact bets max to avoid scope sprawl?

## 6) Source links (audited)

Primary repos/docs:

- https://github.com/nathom/streamrip
- https://github.com/slskd/slskd
- https://github.com/rogerfar/rdt-client
- https://github.com/beetbox/beets
- https://github.com/Prowlarr/Prowlarr
- https://github.com/Lidarr/Lidarr
- https://github.com/navidrome/navidrome
- https://github.com/jellyfin/jellyfin
- https://github.com/TheWicklowWolf/Lidify
- https://github.com/Dodelidoo-Labs/sonobarr
- https://github.com/MrRobotoGit/DiscoveryLastFM
- https://github.com/metabrainz/troi-recommendation-playground
- https://listenbrainz.readthedocs.io/en/latest/users/api/recommendation.html
- https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api
- https://developer.spotify.com/documentation/web-api/concepts/quota-modes
- https://developer.spotify.com/documentation/web-api/reference/get-recommendations
- https://developer.spotify.com/documentation/web-api/reference/get-several-audio-features
- https://github.com/chroma-core/chroma
- https://github.com/qdrant/qdrant
- https://qdrant.tech/documentation/
- https://github.com/LAION-AI/CLAP
- https://github.com/tencent-ailab/MuQ
- https://github.com/minzwon/musicfm
- https://huggingface.co/m-a-p/MERT-v1-95M
- https://github.com/Open-LLM-VTuber/Open-LLM-VTuber
- https://github.com/nbonamy/witsy
- https://github.com/smore-inc/clippy.js

Forum/community signal:

- https://www.reddit.com/r/selfhosted/comments/1hcqdv6/what_do_you_use_for_music_discovery_and/
- https://www.reddit.com/r/selfhosted/comments/1frrx4a/how_i_built_a_music_discovery_tool_for_lidarr/
