# Lyra Gap Registry

Last audited: March 9, 2026

This file tracks the open canonical product gaps that keep Lyra from fully matching its intended identity.

## Active Gap Matrix

| ID | Area | Status | Implemented Now | Missing Or Partial | Legacy Sources To Inspect Next |
| --- | --- | --- | --- | --- | --- |
| G-063 | Composer and playlist intelligence depth | partial, active | Canonical composer pipeline now includes typed intent, provider-parse sanitization, graph-aware route scoring, act-shaped sequencing, feedback-aware route pressure, mood-pressure phase shaping, first-class scene exits, Lyra-read summaries, route audition teasers, deploy-time composer diagnostics, a first canonical Spotify evidence/gap panel in the Lyra workspace, Spotify-driven missing-world pressure inside route flavor and novelty selection, and `explain_track` now emits artist graph evidence (connections table, top-3 by strength, with connection-type labels) as structured EvidenceItems | Arc template evaluation in playlist sequencing and playlust 4-act authorship remain unported | `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, `oracle/arc.py`, `oracle/mood_interpreter.py`, `oracle/taste_backfill.py` |
| G-064 | Discovery graph and bridge depth | largely complete | Related-artist and graph scaffolding exist, the composer has distinct safe/interesting/dangerous lanes, scene-exit logic, and scout-style scene-family targeting; Discover exposes route-handoff, Spotify missing-world recovery, a Genre Hunt panel (genre pair selector, bridge-artist chips, Scout target results, Ask Lyra prompts), and a Deep Cuts panel (obscurity × acclaim scoring, rank display); Artist page exposes lazy-loaded Scout Exits panel with 3-lane UI and play/bridge/hunt/Ask Lyra actions | ListenBrainz weather and full Discogs-backed Scout multi-provider fusion remain Python-only (tagged dormant in BACKLOG_TAGS.md) | `oracle/graph_builder.py`, `oracle/scout.py`, `oracle/recommendation_broker.py` |
| G-061 | Explainability and provenance breadth | partial | Provenance, confidence, saved reason summaries, and reopenable composer-run history now exist; live and saved playlist detail retain structured reason payloads, phase roles, and inferred-vs-explicit splits; Discover recommendations now carry EvidenceItem + whyThisTrack + inferredByLyra at composer payload depth with provider badges per card; backend now has `search_excavation_surface` (grouped facets + route hints) as a canonical Search contract | Saved playlist detail and broader recommendation surfaces still lack the full richer reason model; Library UI/search routes have not fully switched to the new canonical search-excavation surface yet | `oracle/explain.py`, `oracle/explainability.py`, `oracle/enrichers/unified.py` |
| G-060 | Acquisition workflow parity | implemented with residual risk | Canonical acquisition lifecycle, queue authority, and horizon intelligence infrastructure exist | Remaining Python executor removal and metadata-validator parity still open | `oracle/acquirers/waterfall.py`, `oracle/acquirers/validator.py`, `oracle/acquisition.py` |
| G-062 | Curation workflows | partial | Canonical library and playlist basics exist | Duplicate stewardship, cleanup preview depth, and rollback ergonomics remain incomplete | `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py` |
| G-065 | Packaged desktop confidence | partial | Canonical runtime builds and launches locally; Cassette-branded NSIS/MSI bundles now build from the canonical Tauri app | Clean-machine installer and long-session packaged proof remain open until the new installer is validated outside the dev machine | packaged validation scripts and soak artifacts |

## Execution Order

1. `G-063` Composer and playlist intelligence depth
2. `G-064` Discovery graph and bridge depth
3. `G-061` Explainability and provenance breadth
4. `G-060` Remaining acquisition runtime risk
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

## Dormant Concept Tags

Concepts explicitly identified as backlogged, unported, or not-yet-started are tagged in `docs/BACKLOG_TAGS.md`.
Each is marked `**[ConceptName?]**` — acknowledged and dormant, not in active execution.
Consult that file before starting work on any capability listed as "Mostly unported" or "Not started" above.

## Config Reality

Provider and config plumbing already exists.
Future work should continue to reuse:

- provider config records in SQLite
- capability metadata in Rust
- provider validation hooks
- OS keyring support

Do not invent a parallel credential system for composer or LLM work.
