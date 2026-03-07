# Provider Expansion Research - Official Sources Pass

Date: 2026-03-06
Session: S-20260306-26
Scope: current official-source grounding for later provider/data-source expansion without touching Wave 2 build files

## 1) Why this pass exists

Wave 2 build/release governance is active elsewhere.

This pass uses only official provider documentation to turn later metadata/recommendation ideas into safer implementation targets for Lyra.

## 2) Official-source findings

### A. MusicBrainz is broader than the current use

Official MusicBrainz API docs confirm:

- the API root is `https://musicbrainz.org/ws/2/`
- JSON is available via `Accept: application/json` or `fmt=json`
- the service supports core entities including `artist`, `event`, `recording`, `release`, `release-group`, `series`, `work`, `label`, and more
- lookups, browse requests, and `inc=` relationship expansions are first-class features
- clients must use a meaningful user agent and stay within one call per second

Lyra implication:

- current credit and identity work should grow into an MBID-centric enrichment layer, not isolated one-off fetches
- `release-group`, `series`, `event`, and `label` context are justified by the official API surface, not just speculative feature creep

### B. Cover Art Archive is ready for release and release-group identity

Official Cover Art Archive docs confirm:

- `/release-group/{mbid}/` returns JSON cover-art listings
- `/release-group/{mbid}/front` returns the canonical front-art redirect
- release-group responses include image URLs, thumbnails, and the specific release the art came from

Lyra implication:

- route heroes, playlist detail, and now-playing surfaces can use release-group canonical art without inventing a new art pipeline
- release identity and artwork should be tied to MBID-centric enrichment instead of ad hoc image lookup

### C. ListenBrainz offers more than top recordings

Official ListenBrainz docs confirm:

- collaborative recording recommendations exist at `/1/cf/recommendation/user/(mb_username)/recording`
- similar-user data exists at `/1/user/(mb_username)/similar-users`
- playlist endpoints include playlist fetch, XSPF export, creation, copy, and export/import-related surfaces

Lyra implication:

- current ListenBrainz usage is still shallow
- future provider work should use similar-user and collaborative recommendation data for richer community evidence
- playlist surfaces can inform interop and recommendation explainability later, especially when tied back to MusicBrainz recording IDs

### D. setlist.fm is useful but should remain optional

Official setlist.fm docs confirm:

- access requires an API key
- requests must include the `x-api-key` header

Lyra implication:

- live-performance context is viable, but should stay optional and soft-ranked
- setlist-derived signals should enrich sequencing or ritual/live-context inference, not become a required core dependency

## 3) Repo-grounded design direction

Based on the current repo and these official docs, the best provider-expansion order is:

1. MusicBrainz identity and relationship expansion
2. Cover Art Archive release-group art integration
3. ListenBrainz collaborative and similar-user expansion
4. setlist.fm optional live-context enrichment

This matches Lyra’s current architecture better than chasing broad new platforms or rebuilding downloader behavior.

## 4) Recommended implementation posture

- Keep provider adapters normalized and versioned through one broker contract
- Treat MusicBrainz as canonical identity/context, not popularity ranking
- Treat Cover Art Archive as enrichment, not a recommender
- Treat ListenBrainz as community/collaborative signal, not sole truth
- Treat setlist.fm as optional context, not a hard dependency

## 5) Concrete fit with local modules

The likely integration anchors remain:

- `oracle/recommendation_broker.py`
- `oracle/integrations/listenbrainz.py`
- `oracle/enrichers/credit_mapper.py`
- `desktop/renderer-app/src/app/UnifiedWorkspace.tsx`

The new specs created alongside this note are the intended contracts:

- `docs/specs/SPEC-003_LYRA_DATA_ROOT.md`
- `docs/specs/SPEC-004_RECOMMENDATION_PROVIDER_CONTRACT.md`
- `docs/specs/SPEC-005_UI_PROVENANCE_AND_DEGRADED_STATES.md`
- `docs/specs/SPEC-006_PROVIDER_HEALTH_AND_WATCHLIST.md`

## 6) Sources

- MusicBrainz API: https://musicbrainz.org/doc/MusicBrainz_API
- Cover Art Archive API: https://musicbrainz.org/doc/Cover_Art_Archive/API
- ListenBrainz Recommendations: https://listenbrainz.readthedocs.io/en/latest/users/api/recommendation.html
- ListenBrainz Core API: https://listenbrainz.readthedocs.io/en/latest/users/api/core.html
- ListenBrainz Playlist API: https://listenbrainz.readthedocs.io/en/latest/users/api/playlist.html
- setlist.fm API: https://api.setlist.fm/docs/1.0/index.html
