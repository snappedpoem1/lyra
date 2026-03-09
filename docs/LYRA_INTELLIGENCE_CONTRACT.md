# Lyra Intelligence Contract

Last updated: March 8, 2026

## Purpose

This document is the canonical product and implementation contract for Lyra intelligence.

Lyra is a vibe-to-journey music intelligence, discovery, and curation system with native playback.
Lyra is not a media player with AI features.

The front door is the Lyra composer.

## Composer Contract

The Lyra composer is a creative-intent surface, not a filter box.

It must accept:

- freeform vibe prompts
- refinement prompts
- bridge prompts
- explanation prompts
- playlist steering prompts
- adjacency and discovery prompts

Examples:

- `edm fire storm trickling into chill undercurrent of lofi covers`
- `sad bedroom static that eventually forgives me`
- `take this playlist and make the middle third less obvious`
- `give me a path from this artist into something adjacent but less obvious`
- `why is this track here`

Composer behavior must follow this flow:

`prompt -> intent parse -> retrieval -> scoring/reranking -> sequencing -> explanation`

Not:

`prompt -> LLM hallucinates playlist -> ship it`

## Response Roles

Lyra must support four explicit operating roles:

### Recommender

Suggests tracks, artists, albums, playlists, or directions.

### Coach

Helps the user sharpen taste, refine prompts, and choose between directions.

### Copilot

Works interactively on shaping, revising, or steering playlists and discovery paths.

### Oracle

Explains hidden relationships, arc logic, bridge choices, contrast, adjacency, and evidence.

These roles must not be collapsed into generic “chat”.

## Structured Intent Contract

Creative language must be parsed into a typed `PlaylistIntent`.

At minimum, the canonical model must support:

- prompt and prompt role
- source energy / opening state
- destination energy / landing state
- transition style
- emotional arc
- texture / timbre descriptors
- explicit entities
- familiarity vs novelty preference
- discovery aggressiveness
- user steer / modifiers
- exclusions / avoidances
- explanation depth
- sequencing notes
- confidence / ambiguity notes

The current canonical implementation is the Rust `PlaylistIntent` model in `crates/lyra-core/src/commands.rs`.

## LLM Provider Contract

Cloud and local LLMs are first-class intelligence providers.

The canonical runtime must expose:

- typed provider abstraction
- local provider support
- cloud provider support
- explicit provider selection
- fallback behavior
- degraded-mode behavior

LLMs are responsible for:

- interpreting vague or poetic language
- refining ambiguous intent
- producing short explanation/narrative language

LLMs are not responsible for:

- inventing tracks that are not in the library
- replacing retrieval, ranking, or sequencing
- fabricating evidence
- acting as the source of truth for final track choice

Current canonical implementation:

- Local provider: `ollama`
- Cloud providers: `openai`, `openrouter`, `groq`
- Selection and fallback state are returned as `ComposerProviderStatus`
- Provider preference lives in app settings
- Ranking and sequencing remain deterministic in Rust

## Deterministic Pipeline Contract

The canonical composer pipeline must stay local and deterministic after intent parse:

1. retrieve candidates from local library data
2. score/rerank for phase fit, transition quality, novelty/familiarity target, and taste fit
3. sequence into visible phases
4. attach track-level reason payloads
5. persist reason payloads when saving

Current canonical implementation:

- Rust pipeline in `crates/lyra-core/src/intelligence.rs`
- phase plan exposed as `PlaylistPhase`
- track-level reasons exposed as `TrackReasonPayload`
- saved playlists persist reason summary plus JSON payload in `playlist_track_reasons`

## Explainability Contract

Lyra must be able to answer:

- why this track
- why this next
- what phase this belongs to
- what evidence supported the choice
- what came from explicit prompt language
- what was inferred by Lyra
- whether language help came from a provider or from heuristic fallback

Reason payloads are not optional metadata.
They are part of the product contract.

## Discovery Contract

Lyra must behave as a discovery system, not only as a playlist maker.

The product must support:

- bridge tracks
- related artists with explanation
- “less obvious” and “more adventurous” steering
- movement between scenes, moods, and textures
- user education about why transitions work

Composer, discovery, and explanation are one product lane, not separate afterthoughts.

## UI Contract

The canonical UI must expose:

- parsed intent summary
- selected provider and fallback mode
- visible arc or phases
- track-level why this is here
- saved reason durability

Current canonical implementation lands this first slice on the playlists route and settings route.

## Degraded Mode Contract

When no LLM provider is configured or reachable:

- Lyra must still parse intent heuristically
- Lyra must still retrieve, rerank, sequence, and explain deterministically
- UI must say that heuristic fallback was used
- the app must not pretend the prompt was fully understood by a provider

## Non-Negotiable Framing

If a future change makes Lyra read primarily as:

- a media player
- a playback shell
- a queue app
- a library manager with AI garnish

that change violates this contract.
