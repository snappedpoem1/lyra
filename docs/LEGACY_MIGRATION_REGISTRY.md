# Legacy Migration Registry

Last updated: March 8, 2026

## Purpose

This file is the authoritative cross-reference between legacy Python capabilities and their Rust migration targets.

> Capabilities marked "Mostly unported" or "Largely unported" are tagged as dormant in `docs/BACKLOG_TAGS.md`.
> Consult that file before starting any port — do not attempt to implement dormant tags without first promoting them to WORKLIST.md.

It is not just a port checklist.
It identifies which legacy behaviors matter most because they embody Lyra's real product identity:

- explainable recommendation
- playlist authorship
- discovery graph depth
- taste memory and dimensional scoring
- provenance-aware enrichment
- acquisition and curation workflows that reinforce the intelligence layer

Read this alongside:

- `docs/ROADMAP_ENGINE_TO_ENTITY.md` for sequencing
- `docs/MISSING_FEATURES_REGISTRY.md` for active gaps
- `docs/MIGRATION_PLAN.md` for migration discipline

## Config And Credential Note

The repo already contains real provider/config plumbing.
Relevant surfaces include:

- Python `.env` loading in `archive/legacy-runtime/oracle/config.py`, `archive/legacy-runtime/oracle/api/app.py`, `archive/legacy-runtime/lyra_api.py`, and integration modules
- Rust env import and provider mapping in `crates/lyra-core/src/providers.rs`
- Rust `provider_configs` persistence
- Rust provider validation and OS keyring support

Do not expose secret values.
Do not assume integrations are blocked just because a canonical UI workflow is incomplete.

## Priority Buckets

### Tier 1 - Identity-defining logic to port with high fidelity

- recommendation broker and explainability
- vibe/playlust/playlist-reason generation
- graph builder and scout discovery
- taste profile updates and backfill
- dimensional scoring
- unified enrichment, MBID identity, credits, and biography

### Tier 2 - Supporting workflows that materially affect trust and usefulness

- acquisition waterfall behavior and prioritization
- ingest watcher and confidence
- duplicate detection and curation flows
- diagnostics and provider-health workflows

### Tier 3 - Mostly runtime/scaffolding or secondary utility

- Flask bootstrap and blueprint registration mechanics
- Python-side app startup wrappers
- legacy transport layers that should not return as canonical runtime

## Migration Table

| Legacy capability | Primary Python source(s) | Why It Matters | Canonical target | Current status |
|---|---|---|---|---|
| Recommendation broker | `oracle/recommendation_broker.py`, `oracle/api/blueprints/recommendations.py` | Core explainable discovery behavior and provider-orchestration logic | `lyra-core::oracle`, Svelte Discover surfaces | Partially ported; richer evidence and reasoning still missing |
| Explainability and reasons | `oracle/explain.py`, `oracle/explainability.py` | Turns recommendation and playlist output into user-legible decisions | `lyra-core::oracle`, playlist/recommendation UI | Partially ported; not broad enough in canonical UI |
| Playlist intelligence and vibe generation | `oracle/playlust.py`, `oracle/vibes.py`, `oracle/api/blueprints/vibes.py` | Core playlist authorship and narrative-generation identity | `lyra-core::playlists`, `lyra-core::oracle`, Playlists UI | Largely unported as a first-class canonical workflow |
| Graph builder and discovery graph | `oracle/graph_builder.py`, `oracle/api/blueprints/discovery.py` | Needed for constellation exploration and non-flat artist discovery | `lyra-core::oracle`, Artist/Discover UI | Mostly unported |
| Scout and bridge discovery | `oracle/scout.py`, ListenBrainz/Discogs integrations | Enables bridge-artist and cross-genre discovery | `lyra-core::oracle`, discovery actions | Mostly unported |
| Dimensional scoring | `oracle/scorer.py`, related score consumers | Gives Lyra visible emotional/taste structure | `lyra-core::enrichment`, `lyra-core::oracle` | Partially represented; full live scorer not ported |
| Taste learning and backfill | `oracle/taste.py`, `oracle/taste_backfill.py`, player hooks | Makes recommendations and playlists user-owned over time | `lyra-core::oracle`, playback feedback flows | Early Rust baseline exists; richer behavior still in Python |
| Unified enrichment flow | `oracle/enrichers/unified.py` and provider enrichers | Central source of provenance-aware metadata gathering | `lyra-core::enrichment` | Partially ported provider-by-provider |
| MBID identity spine | `oracle/enrichers/mb_identity.py` | Stabilizes artist/recording identity and provenance | `lyra-core::enrichment`, Library/Artist views | Partially ported |
| Credits and artist biography | `oracle/enrichers/credit_mapper.py`, `oracle/enrichers/biographer.py` | Deepens trust, context, and artist exploration | `lyra-core::enrichment`, `lyra-core::library`, Artist UI | Mostly unported |
| Acquisition waterfall and prioritizer | `oracle/acquirers/waterfall.py`, `oracle/acquirers/taste_prioritizer.py`, `oracle/acquirers/guard.py`, `oracle/acquirers/validator.py` | Feeds the library intelligently and preserves solved acquisition flow | `lyra-core::acquisition` | Queue exists; meaningful process logic still heavily Python-backed |
| Ingest watcher and confidence | `oracle/ingest_watcher.py`, `oracle/ingest_confidence.py` | Makes acquisition trustworthy and reduces silent bad imports | `lyra-core::library`, `lyra-core::acquisition` | Mostly unported |
| Duplicates and curation | `oracle/duplicates.py`, `oracle/curator.py`, `oracle/organizer.py` | Needed for safe local stewardship and cleanup | `lyra-core::library`, curation UI | Mostly unported |
| Diagnostics and provider-health flows | `oracle/doctor.py`, `oracle/status.py`, `oracle/provider_health.py` | Supports trust, degraded-state honesty, and operator clarity | `lyra-core::commands`, settings/diagnostics UI | Partially ported |
| Python runtime scaffolding | `oracle/api/app.py`, `oracle/runtime_services.py`, `lyra_api.py` runtime startup sections | Important for reference only, not for restoration of runtime shape | none as runtime; inspect for config/process clues only | Obsolete as canonical runtime |

## Porting Rules

When touching a capability above:

1. Read the Python implementation first.
2. Separate runtime scaffolding from product logic.
3. Preserve the solved semantics that matter to users.
4. Reuse existing provider/env/config plumbing.
5. Do not claim a feature is complete in docs unless the canonical runtime actually exposes it.
6. Record which legacy source informed the canonical implementation.

## What Not To Recreate Blindly

- provider/env loading paths that already exist
- recommendation reasoning patterns already implemented in Python
- acquisition process sequencing already implemented in Python
- playlist-reason generation already implemented in Python
- graph/discovery workflows already implemented in Python
