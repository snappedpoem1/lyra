# Lyra Gap Registry

Last audited: March 8, 2026

This file tracks the open canonical product gaps that keep Lyra from fully matching its intended identity.

## Active Gap Matrix

| ID | Area | Status | Implemented Now | Missing Or Partial | Legacy Sources To Inspect Next |
| --- | --- | --- | --- | --- | --- |
| G-063 | Composer and playlist intelligence depth | partial, active | Canonical composer pipeline now exists in Rust/Tauri/Svelte: typed `PlaylistIntent`, local/cloud LLM provider abstraction, deterministic retrieval/reranking/sequencing, visible phases, provider fallback reporting, and persisted reason payloads on save | Prompt handling is still concentrated in playlist drafting; refinement loops, deeper semantic retrieval, stronger bridge scoring, and broader explanation coverage remain thin | `oracle/vibes.py`, `oracle/playlust.py`, `oracle/explain.py`, `oracle/arc.py` |
| G-064 | Discovery graph and bridge depth | partial | Related-artist and graph scaffolding exist in the canonical runtime | Bridge prompts, adjacency journeys, and explanation-rich discovery are still too thin | `oracle/graph_builder.py`, `oracle/scout.py`, `oracle/recommendation_broker.py` |
| G-061 | Explainability and provenance breadth | partial | Provenance, confidence, and saved reason summaries exist; composer drafts now carry structured reason payloads and provider mode | Inferred-vs-explicit reasoning, why-this-next coverage, and broader surface consistency remain incomplete | `oracle/explain.py`, `oracle/explainability.py`, `oracle/enrichers/unified.py` |
| G-060 | Acquisition workflow parity | implemented with residual risk | Canonical acquisition lifecycle, queue authority, and horizon intelligence infrastructure exist | Remaining Python executor removal and metadata-validator parity still open | `oracle/acquirers/waterfall.py`, `oracle/acquirers/validator.py`, `oracle/acquisition.py` |
| G-062 | Curation workflows | partial | Canonical library and playlist basics exist | Duplicate stewardship, cleanup preview depth, and rollback ergonomics remain incomplete | `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py` |
| G-065 | Packaged desktop confidence | partial | Canonical runtime builds and launches locally | Clean-machine installer and long-session packaged proof remain open | packaged validation scripts and soak artifacts |

## Execution Order

1. `G-063` Composer and playlist intelligence depth
2. `G-064` Discovery graph and bridge depth
3. `G-061` Explainability and provenance breadth
4. `G-060` Remaining acquisition runtime risk
5. `G-062` Curation workflows
6. `G-065` Packaged desktop confidence

## Config Reality

Provider and config plumbing already exists.
Future work should continue to reuse:

- provider config records in SQLite
- capability metadata in Rust
- provider validation hooks
- OS keyring support

Do not invent a parallel credential system for composer or LLM work.
