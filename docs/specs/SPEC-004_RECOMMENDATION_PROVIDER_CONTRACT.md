# SPEC-004: Recommendation Provider Contract and Evidence Payload

## 1. Objective

Turn recommendation assembly into a provider-contract system with normalized candidate shapes, explicit degradation behavior, and first-class evidence payloads.

This spec is for the later metadata/recommendation wave and is written to support:

- local graph and embedding sources
- Last.fm
- ListenBrainz
- MusicBrainz-derived context
- Cover Art Archive-derived release identity
- optional live-context providers later

## 2. Core Principles

- Lyra orchestrates and ranks; it does not pretend every provider is equally authoritative.
- Every surfaced recommendation must carry explainable provenance.
- Provider failure or degradation must be visible in machine-readable output.
- The API contract must be versioned before broadening providers.

## 3. Provider Adapter Contract

Each provider adapter must return a normalized result object with:

- `provider`: stable provider key
- `status`: `ok`, `empty`, `degraded`, or `failed`
- `message`: short provider status summary
- `seed_context`: normalized statement of what the provider used as input
- `candidates`: zero or more normalized recommendation candidates
- `errors`: structured provider errors when degraded or failed
- `timing_ms`: request/compute duration

### 3.1 Candidate shape

Each candidate must include:

- `track_id`: local track id if resolvable
- `external_identity`: provider-specific ids and canonical identifiers
- `artist`
- `title`
- `album` when known
- `score`: provider-local score
- `confidence`: normalized 0-1 confidence
- `novelty_band_fit`: `safe`, `stretch`, or `chaos`
- `evidence`: list of machine-readable evidence items
- `provenance_label`: short human-readable provider label
- `availability`: local, acquisition-lead, or unresolved

### 3.2 Evidence item shape

Each evidence item must include:

- `type`
- `source`
- `weight`
- `text`
- `raw_value` when useful for debugging or UI traces

Example evidence types:

- `embedding_neighbor`
- `similar_track`
- `community_popularity`
- `shared_work`
- `shared_release_group`
- `listener_cluster`
- `live_rotation_signal`

## 4. Broker Output Contract

The broker response must be versioned.

Add:

- `schema_version`
- `seed`
- `provider_reports`
- `recommendations`
- `degraded`
- `degradation_summary`

### 4.1 `provider_reports`

The broker must return provider-level status objects even when a provider yields no candidates.

This is required so the UI can show:

- which providers were active
- which were empty
- which failed
- whether the final list is narrow because of provider degradation rather than true absence

### 4.2 Merged recommendation output

Each merged recommendation must preserve:

- contributing providers
- merged evidence list
- merged confidence
- final broker score
- provenance summary string
- explanation text suitable for immediate UI rendering

## 5. Feedback Contract

Recommendation feedback must support explicit and passive outcomes.

### 5.1 Explicit outcomes

- keep
- queue
- play
- skip
- acquire_request
- dismiss

### 5.2 Passive outcomes

Plan for later support of:

- replayed within session
- replayed within 7 days
- saved to vibe/playlust
- short-abandon

The persisted event model must be idempotent enough to avoid double-counting obvious retries or duplicate UI posts.

## 6. Provider Rules

### 6.1 Last.fm

- Use as a recommendation and affinity signal, not as sole truth.

### 6.2 ListenBrainz

- Use community and collaborative signals.
- Preserve provider-level status when the service is reachable but yields no relevant local matches.

### 6.3 MusicBrainz

- Use for canonical identity and relationship context.
- Respect rate limiting and caching.

### 6.4 Cover Art Archive

- Treat as release-identity and artwork enrichment, not ranking authority by itself.

### 6.5 Spotify

- Do not treat Spotify recommendation/audio-feature endpoints as a strategic backbone.
- Spotify remains auxiliary only where policy-safe and already-supported.

## 7. UI Expectations

The API must make these UI behaviors possible without extra inference:

- source chips per recommendation
- confidence bands
- plain-language “why this” copy
- technical trace/details view
- visible degraded/failure states when provider coverage is weak

## 8. Testing Requirements

Each provider adapter must have contract coverage for:

1. success with candidates
2. reachable but empty result
3. timeout or upstream failure
4. malformed payload handling
5. degraded local-resolution case

Broker-level tests must cover:

1. local-only recommendation assembly
2. mixed-provider merge
3. duplicate candidate merge across providers
4. degraded provider visibility in output
5. evidence preservation after merge
6. feedback persistence against the versioned contract

## 9. Acceptance Criteria

This spec is satisfied when:

- recommendation providers share one normalized contract
- broker responses are schema-versioned
- every recommendation can show machine-readable and plain-language rationale
- degradation is explicit instead of silent
- the UI can render provenance and failure states directly from API output
