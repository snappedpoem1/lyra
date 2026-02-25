# Backend 1.0 Objectives and Execution TODO

## North-Star Outcome
Ship a stable Lyra backend where metadata, identity, and graph intelligence are persisted and reused so playback/search/agent flows do not re-pull full external API data on every request.

## Objective 1: Canonical Identity and Subgenre Model
- Goal: Every active track can carry canonical IDs and subgenre context.
- Success criteria:
  - `tracks` has: `subgenres`, `artist_mbid`, `recording_mbid`, `release_mbid`, `release_group_mbid`, `isrc`, `discogs_release_id`, `metadata_source`, `canonical_confidence`, `last_enriched_at`.
  - Validation pass updates these fields when confidence is acceptable.
  - `genre` + `subgenres` population is measurable and improving over time.

## Objective 2: Provider Pull Reduction (Persistent Cache)
- Goal: Prevent repeated full upstream pulls when the same artist/track gets queued again.
- Success criteria:
  - Discogs/MusicBrainz/iTunes lookups in validator are cache-first with TTL.
  - Lore MusicBrainz calls are cache-first with TTL.
  - Cache hit/miss behavior is inspectable in `enrich_cache`.

## Objective 3: Reliable Connection Graph
- Goal: Lore/scout relationship features run cleanly against current schema.
- Success criteria:
  - `/api/lore/trace` writes rows into `connections`.
  - `/api/lore/connections` returns rows without SQL errors.
  - Scout local mood/genre discovery works against current `tracks` columns.

## Objective 4: Operational Validation API
- Goal: Run metadata validation as an API operation, not only CLI.
- Success criteria:
  - New `/api/library/validate` route with bounded controls (`limit`, `confidence`, `workers`, `only_unvalidated`).
  - Results include fixed/validated/failed counters for dashboarding.

## Completed Changes (Current Iteration)
- Fixed schema mismatches in:
  - `oracle/lore.py` (connections now uses `source/target/evidence` schema).
  - `oracle/scout.py` (uses `tracks.filepath` instead of non-existent `file_path`).
- Added persistent provider cache helper module:
  - `oracle/enrichers/cache.py`.
- Added cache-backed validation lookups:
  - `oracle/acquirers/validator.py` for MusicBrainz, Discogs, iTunes.
- Expanded validation result model:
  - carries `subgenres`, MBIDs, ISRC and release IDs.
- Added API validation execution route:
  - `POST /api/library/validate`.
- Expanded track schema evolution path:
  - canonical metadata + subgenre columns in `oracle/db/schema.py`.

## Open 1.0 TODO List
1. Run DB migration in apply mode and verify new columns/indexes on `lyra_registry.db`.
2. Backfill validation in batches (cache-aware), then measure:
   - `% tracks with genre`
   - `% tracks with subgenres`
   - `% tracks with canonical IDs`.
3. Add cache observability endpoint:
   - per-provider hit/miss/stale counts and recent keys.
4. Add enrichment freshness policy:
   - skip revalidation if `last_enriched_at` within provider TTL unless `force=true`.
5. Add artist-level materialized profile cache table:
   - denormalized artist facts/relationships for fast agent and UI rendering.
6. Add regression tests:
   - schema idempotence includes new canonical fields.
   - validator cache path (cached hit avoids network).
   - lore/scout smoke against active schema columns.
7. Wire web UI/status pages to show:
   - validation backlog,
   - cache utilization,
   - metadata coverage KPIs.

## Runtime/Quality Guardrails
- Keep all DB writes parameterized.
- Keep all provider calls bounded by timeout + retry + cache.
- Avoid broad refreshes during queue processing; prefer targeted refresh by stale keys only.
