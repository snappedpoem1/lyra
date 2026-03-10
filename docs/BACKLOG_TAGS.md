# Backlog Tags — Acknowledged-But-Dormant Concepts

Last updated: March 9, 2026

These concepts are explicitly recognized as incomplete, unported, or not yet started.
They are tagged here so they are not lost and not accidentally over-engineered.

**Protocol:** Each entry is bolded with a `?` suffix — meaning *acknowledged, not active*.
When a concept graduates to active work, move it to WORKLIST.md and remove it here.

---

## Core Intelligence (Unported Legacy)

- **[Playlist Authorship and Vibe Generation?]** — `oracle/playlust.py`, `oracle/vibes.py` largely unported as a first-class canonical workflow. Source behavior exists in legacy Python but no canonical Rust equivalent yet.
- **[Recommendation Broker Multi-Source Fusion?]** — `oracle/recommendation_broker.py` richer evidence and multi-provider orchestration still missing from canonical Rust.
- **[Semantic Interpretation Port?]** — `oracle/vibes.py` semantic interpretation not yet ported into canonical Rust behavior.
- **[Dimensional Scoring Live Port?]** — `oracle/scorer.py` full live scorer not ported; only partially represented.
- **[Taste Learning Richer Behavior?]** — Early Rust baseline exists; full `oracle/taste.py` + `oracle/taste_backfill.py` richer behavior still in Python.

---

## Discovery and Graph

- **[Discovery Graph and Constellation?]** — `oracle/graph_builder.py` mostly unported. Needed for constellation-style artist exploration and non-flat discovery.
- **[Scout as First-Class Discovery Lane?]** — `oracle/scout.py` mostly unported. Bridge-artist and cross-genre discovery not yet a visible canonical lane.
- **[Community Weather Evidence Layer?]** — ListenBrainz similar-artist chain as visible optional evidence. Python-only today; no canonical exposure.
- **[Discogs-Backed Scout Fusion?]** — Multi-provider Discogs + Scout fusion remains Python-only.
- **[Adjacency Semantic and Lineage Evidence?]** — Adjacency reasoning beyond local scoring into stronger semantic/lineage evidence not yet built.
- **[Discover and Artist Typed Route Grammar?]** — Discover/Artist surfaces still lag the composer's typed safe/interesting/dangerous + direct/scenic/contrast grammar.
- **[Scene-Exit Language in Artist and Discovery?]** — Scene-exit/route-audition language not yet carried into artist and discovery pages outside the composer workspace.

---

## Explainability

- **[Library Excavation as Canonical Search Surface?]** — Library excavation still partially embedded in catalog UI; canonical Search surface not yet built.
- **[Discovery and Artist Explanation Parity?]** — Recommendation detail, artist adjacency, and non-playlist surfaces still lack full reason payload depth.
- **[Inferred-vs-Explicit Visibility Across Surfaces?]** — Inferred-vs-explicit reasoning not yet visible on every recommendation-bearing surface.

---

## Taste and Memory

- **[Route Audition Outcome Feedback Loop?]** — Accepted/rejected audition outcomes not yet fed back into pressure memory.
- **[Curation Behavior Memory Feed?]** — Curation actions not yet feeding memory when evidence is strong enough.
- **[Spotify Evidence as First-Class Signal?]** — Spotify history and library evidence not yet first-class personal signal in memory.
- **[Long-Lived Tendency Promotion?]** — Promotion of tendencies after evidence thresholds not yet implemented.

---

## Spotify and Missing-World

- **[Spotify Import Freshness Workflow?]** — Import freshness and status not yet surfaced as a first-class product workflow.
- **[Rebuild Missing World Flow?]** — Dedicated "rebuild this missing world" flow not yet built; only summary panels and queue hooks exist.

---

## Identity Spine and Curation

- **[MBID Identity Spine Full Canonicalization?]** — `oracle/enrichers/mb_identity.py` only partially ported; full Rust canonicalization not complete.
- **[Ingest Confidence Trust Pipeline?]** — `oracle/ingest_confidence.py` mostly unported; not yet surfaced as end-to-end trust workflow.
- **[Duplicate Stewardship and Curation Workflows?]** — `oracle/duplicates.py`, `oracle/curator.py` mostly unported; duplicate review, keeper selection, cleanup preview, rollback depth not restored.
- **[Ownership Flows for Vibes and Routes?]** — Save/own flows for vibes, routes, and scene exits not yet as clear as saved playlists.
- **[Credits and Artist Biography Port?]** — `oracle/enrichers/credit_mapper.py`, `oracle/enrichers/biographer.py` mostly unported.

---

## Companion and Ritual

- **[Companion Pulse Event-Driven Behavior?]** — Companion pulse not yet event-driven and purposeful in the canonical runtime.
- **[Native Ritual Features Promotion?]** — Ritual features not yet promoted where they deepen the product.
- **[Now-Playing Route Context?]** — Now-playing context does not yet explain the current route role or what comes next.

---

## Acquisition and Infrastructure

- **[Python Waterfall Executor Replacement?]** — Remaining Python waterfall executor (`oracle/acquirers/waterfall.py`) not yet replaced.
- **[Metadata Validator Parity?]** — `oracle/acquirers/validator.py` parity still open.
- **[Unified Enrichment Flow Port?]** — `oracle/enrichers/unified.py` only partially ported provider-by-provider.
- **[Ingest Watcher Rust Port?]** — `oracle/ingest_watcher.py` mostly unported.

---

## Release Confidence

- **[Clean-Machine Installer Validation?]** — Cassette-branded installer not yet validated on a clean machine.
- **[Long-Session Packaged Confidence Proof?]** — Long-session soak test on packaged build not yet completed.

---

## Active Build Roll (Next Actions — Not Dormant)

These are the live priorities from WORKLIST.md. Do not confuse them with the dormant tags above:

1. `G-063` — Promote Scout, search-as-excavation, and broader route language into Discover and Artist surfaces
2. `G-064` — Expand related-artist and graph surfaces into composer adjacency language
3. `G-061` — Replace Library excavation with a canonical Search surface
4. `G-060` — Python waterfall executor removal + metadata-validator parity
5. `G-062` — Duplicate review, keeper selection, cleanup preview, undo depth
6. `G-065` — Clean-machine installer and long-session confidence proof
