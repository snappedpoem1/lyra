# Whole Dream Checklist

Last updated: March 9, 2026

This checklist is the grounded reconciliation layer for Cassette powered by Lyra.
It is built from:

- canonical truth docs in `docs/`
- surviving specs in `docs/specs/`
- legacy Python behavior in `oracle/`
- research and session records that describe the intended product shape

It is not a wish dump. Each item here is either:

- already canonical
- implemented in legacy and still owed to the canonical runtime
- explicitly spec-backed or research-backed and intentionally promoted into the build

## Product Shell

- [x] Cassette is the shell identity and Lyra is the intelligence identity
- [x] The composer is visually central in the main workspace
- [x] Route comparison is visible in the canonical shell
- [x] Lyra read, confidence, fallback, and diagnostics are visible in the workspace
- [x] Recent Lyra work can be reopened from the shell
- [ ] Discover, Artist, Search, and saved-result surfaces reach the same intelligence depth as the main composer workspace
- [ ] The whole shell feels uniformly intelligence-first instead of having one strong page and several thinner ones

## Lyra Core Intelligence

- [x] Typed composer actions exist for playlist, bridge, discovery, explain, and steer revision
- [x] Weird prompts are parsed as creative intent instead of plain search
- [x] Safe / interesting / dangerous route comparison exists
- [x] Direct / scenic / contrast bridge variants exist
- [x] Scene exits are first-class composer behavior
- [x] Provider-assisted intent parsing is sanitized back into Lyra’s allowed schema
- [x] Provider-authored narrative is constrained by the Lyra contract
- [x] Route audition teasers exist in the canonical workspace
- [x] Challenge behavior exists in bounded form
- [ ] The remaining `oracle/vibes.py` semantic interpretation is ported into canonical Rust behavior
- [ ] The strongest `oracle/playlust.py` authored-journey logic is restored as a first-class canonical workflow, not only act-shaping residue
- [ ] Recommendation-broker style multi-source evidence fusion is complete in canonical Rust
- [ ] Search behaves like excavation and route handoff, not only filtering

## Adjacency, Bridge, and Discovery

- [x] Bridge steps persist preserve/change/adjacency language
- [x] Scene-family targeting from legacy scout logic materially affects composer routes
- [x] Local graph pressure affects composer route scoring
- [x] Scene exits can preserve a live wire while leaving genre or canon
- [ ] Discover and Artist surfaces use the same typed route grammar as the composer
- [ ] Scout is a first-class visible discovery lane in the canonical product
- [ ] Community weather is a visible optional evidence layer, not only a buried idea
- [ ] Adjacency reasoning reaches beyond improved local scoring into stronger semantic and lineage evidence

## Taste Memory and Pressure Memory

- [x] Session posture and rolling taste memory exist
- [x] Repeated steer phrases affect remembered preference pressure
- [x] Accepted and rejected route variants are captured
- [x] Memory language is recency-aware and confidence-aware
- [ ] Route audition outcomes are fed back into pressure memory
- [ ] Curation behavior feeds memory when evidence is strong enough
- [ ] Spotify history and library evidence feed memory as a first-class personal signal
- [ ] Long-lived tendencies are promoted only after explicit evidence thresholds are met

## Spotify History and Missing-World Recovery

- [x] Spotify liked-library queue seeding exists in the canonical runtime
- [x] Cassette now exposes a canonical Spotify evidence and gap summary in the Lyra workspace
- [x] Cassette now shows missing owned-world counts and top missing-world seeds from Spotify data
- [x] Missing Spotify candidates can now be sent into acquisition directly from the workspace
- [x] Spotify-derived missing-world pressure now biases Lyra route flavor, novelty appetite, and explanation when the prompt touches those worlds
- [ ] Spotify import freshness and import status are surfaced as a first-class product workflow
- [ ] Cassette has a dedicated “rebuild this missing world” flow instead of only summary panels and queue hooks
- [x] Spotify gap analysis is visible outside the composer workspace where it improves acquisition and discovery decisions

## Explainability and Provenance

- [x] Live composer results expose why-this-track, why-this-step, and why-this-route language
- [x] Saved playlists persist structured reason payloads
- [x] Composer-run history persists full structured responses
- [x] Fallback and uncertainty remain visible in the workspace
- [x] Composer diagnostics persist to SQLite for deploy-time debugging
- [ ] Discovery, recommendation detail, artist adjacency, and reopened non-playlist results preserve the same explanation depth
- [ ] Inferred-vs-explicit reasoning stays visible on every recommendation-bearing surface

## Identity Spine, Trust, and Ownership

- [x] Local library ownership stays canonical
- [x] Acquisition queue, validator hooks, and trust-related status exist in Rust
- [ ] MBID identity spine is fully canonicalized in Rust
- [ ] Ingest confidence is surfaced as an end-to-end trust pipeline in the product
- [ ] Duplicate stewardship, cleanup preview, and rollback depth are restored as first-class workflows
- [ ] Ownership flows for vibes, routes, and scene exits are as clear as saved playlists

## Companion and Ritual

- [x] Now-playing remains subordinate to intelligence surfaces
- [ ] Companion pulse is event-driven and purposeful in the canonical runtime
- [ ] Native ritual features are promoted where they deepen the product instead of decorating it
- [ ] Now-playing context explains the current route role and what comes next

## Release Confidence

- [x] Canonical runtime builds locally
- [x] Cassette-branded packaging code path exists
- [ ] Clean-machine packaged validation is complete
- [ ] Long-session packaged confidence proof is complete

## Next Build Rule

When choosing what to do next, prefer the item that makes Cassette powered by Lyra feel more perceptive, more owned, and more route-intelligent in the real shell.

Do not spend a pass on cosmetic polish while the unchecked product-defining boxes above are still open.
