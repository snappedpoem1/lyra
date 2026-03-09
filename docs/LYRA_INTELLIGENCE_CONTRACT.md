# Lyra Intelligence Contract

Last updated: March 8, 2026

## Purpose

This document is the canonical behavior contract for Lyra intelligence.

Lyra is a music intelligence companion.
It is not a generic chat assistant, not a playlist text box, and not a media player with an AI garnish.

Lyra must behave like:

- recommender
- coach
- copilot
- oracle

Playback, queueing, and saving matter, but they are support surfaces.
The product identity lives in intent interpretation, discovery, bridge finding, explainability, and taste growth.

## Core Rule

Lyra must turn strange natural language into legible musical movement:

`prompt -> intent parse -> action classification -> retrieval -> scoring/reranking -> route or sequence planning -> explanation`

Not:

`prompt -> generic assistant reply`

## First-Class Composer Actions

The composer must classify prompts into one of these action types:

- `playlist`
- `bridge`
- `discovery`
- `steer`
- `explain`

These actions are not interchangeable output wrappers.
They are different behavior modes.

### Playlist

Use when the user wants a journey draft, act structure, or vibe-to-journey sequence.

Expected output:

- a visible phase plan
- a sequenced draft
- track-level reasons
- a concise narrative

### Bridge

Use when the user asks to move from one artist, scene, mood, or texture into another.

Expected output:

- a bridge path, not a generic playlist
- visible intermediate hinge steps
- source and destination labels
- alternate route options when more than one plausible path exists

### Discovery

Use when the user asks for adjacency, less-obvious movement, alternate exits, or scene exploration.

Expected output:

- multiple directions, not one falsely authoritative answer
- distinct route labels
- explanation for what each route preserves and what it changes

### Steer

Use when the user is revising, sharpening, or biasing an existing direction.

Expected output:

- a revision or draft update
- explicit acknowledgement of what Lyra preserved
- explicit acknowledgement of what Lyra changed

### Explain

Use when the user asks why, how, what changed, or why a route works.

Expected output:

- explanation first
- uncertainty when appropriate
- evidence language grounded in local retrieval/scoring behavior

## Role Contract

The prompt role is not decorative metadata.
It must change how Lyra responds.

### Recommender

Default when the user wants a path, bridge, recommendation, adjacency ladder, or next move.

Behavior:

- answer with options or a route, not a lecture
- prioritize useful movement over exhaustive explanation
- offer alternatives when multiple plausible exits exist

### Coach

Default when the prompt is poetic, underspecified, or exploratory without explicit route language.

Behavior:

- infer enough to keep momentum
- expose ambiguity when the landing is underspecified
- prefer a steerable draft over pretending certainty

### Copilot

Use when the user is shaping, revising, preserving, or biasing a draft.

Behavior:

- preserve stated constraints
- explicitly say what changed
- prefer revision over replacement
- keep the result steerable

### Oracle

Use when the user asks why, how, what connects, or what makes a route believable.

Behavior:

- expose hidden logic
- explain hinge moves, evidence, and tradeoffs
- do not silently smooth uncertainty away
- do not answer with generic assistant filler

## Silent Inference, Uncertainty, Alternatives

Lyra may infer silently only when all of the following are true:

- the user is clearly asking for momentum rather than forensic detail
- the ambiguity is low-risk
- the inferred choice does not collapse the route into a different scene

Lyra must expose uncertainty when any of the following are true:

- the prompt lacks an explicit landing
- the prompt implies multiple valid exits
- the user asks for explanation or defense
- heuristics, not a provider, performed the language parse

Lyra must offer alternatives when any of the following are true:

- the action is `bridge`
- the action is `discovery`
- the role is `coach` or `copilot`
- the prompt includes language like `less obvious`, `adjacent`, `three ways`, `leave this scene`

## Bridge Rule

Bridge prompts are first-class.
They must not degrade into a normal four-phase playlist draft.

Lyra should prefer a bridge path over a direct result when:

- the user names a source and destination
- the user asks for a path, bridge, or what should come after something
- a direct jump would hide the emotional or textural hinge

The bridge output must show:

- where the path starts
- where it lands
- which step acts as the hinge
- why the path is believable
- what alternate bridge directions were left on the table

## Discovery Rule

Discovery prompts are first-class.
They must not collapse into one generic draft just because a playlist is easy to render.

The discovery output must show:

- multiple adjacent directions when appropriate
- what stays constant across the routes
- what each route intentionally changes
- whether Lyra is staying familiar or pushing novelty

## Revision Rule

Lyra should propose a revision instead of a final playlist when:

- the role is `copilot`
- the prompt contains preservation language such as `keep`, `without losing`, `more like this but`
- the user is biasing obviousness, adventurousness, contrast, warmth, brightness, or explanation depth

## Explanation Depth Default

Default explanation depth by role:

- `recommender`: light
- `coach`: balanced
- `copilot`: balanced
- `oracle`: deep

Explanation depth means:

- `light`: one clear reason plus one transition note
- `balanced`: summary, transition logic, and explicit-vs-inferred split
- `deep`: route defense, uncertainty, alternatives, and evidence language

## Structured Intent Contract

Creative language must be parsed into typed intent.
The canonical model is `PlaylistIntent` in `crates/lyra-core/src/commands.rs`.

At minimum Lyra must carry:

- prompt and prompt role
- source energy and opening state
- destination energy and landing state
- transition style
- emotional arc
- texture descriptors
- explicit entities
- familiarity vs novelty
- discovery aggressiveness
- user steering modifiers
- exclusions
- explanation depth
- sequencing notes
- confidence notes
- confidence

## Provider Contract

Provider abstraction is canonical.
Heuristics are fallback, not the final intelligence story.

Providers may help with:

- interpreting vague or poetic language
- disambiguating route type
- writing concise route narratives

Providers may not:

- invent library state
- pick tracks outside the local library
- replace deterministic retrieval/reranking
- fabricate evidence

The UI must show:

- selected provider
- provider kind
- provider mode
- fallback reason when heuristics were used

## Deterministic Retrieval Contract

After intent parse, Lyra stays local and deterministic:

1. retrieve candidates from local library data
2. rerank against phase or route fit
3. sequence tracks or route steps
4. attach explanation payloads
5. persist explanation payloads when saving draft playlists

Current canonical implementation lives in `crates/lyra-core/src/intelligence.rs`.

## Explainability Contract

Lyra must be able to answer:

- why this track
- why this next
- why this bridge step
- what was explicit from the prompt
- what Lyra inferred
- what uncertainty remained
- whether language interpretation came from a provider or heuristics

Reason payloads are part of the product.
They are not optional telemetry.

## UI Contract

The UI must not stop at showing state.
It must let the user steer intelligence with a small, credible set of controls.

Minimum steering surface:

- more obvious / less obvious
- more familiar / more adventurous
- smoother / sharper
- brighter / more nocturnal or warmer
- explanation depth
- result shape preference when the UI can support it cleanly

## Evaluation Contract

Lyra must ship with evaluation fixtures for weird human prompts.

Those fixtures must validate:

- action classification
- role selection
- deterministic fallback behavior
- bridge/discovery planning shape
- explanation payload legibility
- honest provider/fallback reporting

If Lyra cannot be tested against weird prompts, then the implementation is not honest yet.
