# Eleven-of-Ten Horizon Map

Date: 2026-03-06
Session: S-20260306-27
Scope: mine older Lyra wishes that were only partially realized, then ground the next expansion ideas in primary-source documentation without touching Wave 2 build governance

## 1) Why this note exists

Lyra already has more ambition than a normal local music app:

- brokered recommendations
- acquisition waterfall orchestration
- a companion shell
- a scout/discovery identity
- emotional topology instead of plain genre search

The repo also shows a pattern of ideas that were started, then partially parked while the Tauri/runtime unification work took priority.

This note is the "what did we breeze over?" pass.

## 2) Breezed-over wishes that are still valid

### A. Scout is present, but not promoted to a first-class route

Repo evidence:

- `oracle/scout.py` already has Discogs-backed bridge-artist and mood-discovery logic
- `oracle/api/blueprints/intelligence.py` already exposes scout-oriented endpoints
- `oracle/agent.py` still frames Lyra around tool personas like scout, lore, dna, and hunter

Works, but:

- scout feels like backend potential rather than an active product surface
- cross-genre bridge discovery is still isolated from the recommendation broker and main shell

Solution:

- pull scout into the provider-contract era as a named discovery provider, not a side utility
- treat cross-genre bridge results as "controlled surprise" seeds that can be fed into broker ranking and acquisition leads
- give scout a visible lane in Oracle and the Library/right-rail detail flow

### B. Acquisition works, but the cleanup/normalization layer is still under-leveraged

Repo evidence:

- `oracle/integrations/beets_import.py` already exists
- `oracle/enrichers/acoustid.py` already exists
- `oracle/acquirers/validator.py` already blends MusicBrainz, AcoustID, and Discogs

Works, but:

- acquisition quality is still discussed mostly as downloader availability and guard confidence
- post-download canonicalization is not yet a prominent user-facing trust layer

Solution:

- make "acquired -> validated -> normalized -> enriched -> placed" a first-class state machine instead of just background plumbing
- use AcoustID + MusicBrainz identity confirmation as the strongest anti-garbage checkpoint before final import
- use beets as a strict post-acquisition normalization pass where it adds value, not as a replacement for Lyra's own ingest model

### C. The companion exists, but it does not yet feel plugged into the pulse of the app

Repo evidence:

- `desktop/renderer-app/src/features/companion/LyraCompanion.tsx` exists
- settings already expose `companionEnabled` and `companionStyle`
- backend and player event streams already exist

Works, but:

- the companion is mostly shell presence, not a true event-driven intelligence surface
- it does not yet react richly to recommendation provenance, provider degradation, acquisition motion, or cultural/live signals

Solution:

- drive the companion from structured broker, player, provider-health, and acquisition events
- keep output mostly status-first and ritual-first, not chatty
- let it become the smallest visible expression of "Lyra Pulse" instead of a novelty overlay

### D. Cultural pulse is still thin

Repo evidence:

- broker work already uses local, Last.fm, and ListenBrainz
- roadmap and research already point toward explainable discovery and controlled surprise

Works, but:

- current discovery is still mostly library graph + community recommendation
- it lacks stronger "what is happening around this artist/release/live moment?" context

Solution:

- add fresh releases, event/live signals, and social-listening context as optional evidence layers
- do not let "culture" become trend-chasing noise; it should sharpen timing and ritual context

### E. The app shell is strong, but the desktop product layer is still underpowered

Repo evidence:

- Tauri host exists
- tray/media integration exists
- settings, companion, and workspace shell exist

Works, but:

- the desktop experience still behaves more like a powerful internal tool than a deeply finished native music instrument

Solution:

- use native desktop affordances only where they tighten ritual, trust, and continuity
- avoid adding generic app chrome just because Tauri can do it

## 3) Primary-source expansion opportunities

### A. ListenBrainz can provide more current-cultural motion than Lyra uses today

Official docs confirm:

- collaborative recording recommendations are available
- similar-user endpoints exist
- "fresh releases" endpoints exist
- radio-by-tag endpoints exist
- metadata lookups return MusicBrainz-grounded recording detail

Lyra implication:

- ListenBrainz should stop being only a popularity/community source
- it can become Lyra's "community weather" layer:
  - what adjacent listeners are orbiting
  - what is newly arriving
  - which tags/scenes are active

Best fit:

- `oracle/integrations/listenbrainz.py`
- `oracle/recommendation_broker.py`
- future provider-health and provenance UI contracts

### B. MusicBrainz + Cover Art Archive can carry identity far beyond credits

Official docs confirm:

- MusicBrainz WS/2 supports `artist`, `event`, `label`, `recording`, `release`, `release-group`, `series`, and `work`
- `inc=` relationship expansion is first-class
- rate limiting and user-agent discipline matter
- Cover Art Archive exposes release-group front-art and image metadata

Lyra implication:

- MBID should become the canonical spine for identity, lineage, release-group context, event history, and artwork
- Lyra can unify credits, art, release-group identity, and later live/event context without building separate mini-systems

Best fit:

- `oracle/enrichers/credit_mapper.py`
- `oracle/enrichers/musicbrainz.py`
- any future MBID-centric enrichment hub

### C. Discogs is still the best "crate-digger" companion, not the canonical spine

Official docs confirm:

- Discogs exposes database search and release surfaces
- beets has an official Discogs plugin that extends autotagger matching with Discogs releases

Lyra implication:

- keep Discogs for release-hunting, scene adjacency, editions, and bridge-discovery flavor
- do not let Discogs become canonical identity over MusicBrainz
- use it where "crate-digging" is the point, not where stable entity identity is required

Best fit:

- `oracle/scout.py`
- `oracle/deepcut.py`
- `oracle/acquirers/validator.py`

### D. AcoustID is a bigger leverage point than it currently looks

Official docs confirm:

- the AcoustID web service supports fingerprint lookup and lookup by track ID
- it links fingerprint matches to MusicBrainz metadata
- non-commercial applications can register and use it freely

Lyra implication:

- AcoustID should be treated as a hardening layer for acquisition certainty, duplicate resolution, and "mystery file" recovery
- it is one of the cleanest ways to reduce bad imports without overfitting downloader logic

Best fit:

- `oracle/enrichers/acoustid.py`
- `oracle/acquirers/validator.py`
- future duplicate/mismatch remediation flows

### E. beets and Picard are not competitors; they are force multipliers

Official docs confirm:

- beets `mbsync` can refresh metadata for already-imported libraries
- beets `fetchart` and `embedart` can automate art retrieval and embedding
- beets Discogs plugin extends autotagging with Discogs matches
- MusicBrainz Picard genre/tag settings can use MusicBrainz genres and folksonomy tags, and relationship-driven tags expose richer credits/arranger data

Lyra implication:

- Lyra should not reimplement every last metadata cleanup behavior
- a bounded interop layer with beets/Picard-style outputs can make imported files more trustworthy without changing Lyra's core model
- genre/tag ingestion should remain curated because "more tags" is not automatically "better taste intelligence"

Best fit:

- `oracle/integrations/beets_import.py`
- later optional metadata-refresh utilities

### F. Ticketmaster + setlist.fm can create a real live-culture layer

Official docs confirm:

- Ticketmaster Discovery API provides event, attraction, venue, classification, and image resources
- Ticketmaster supports CORS and public discovery use with an API key
- setlist.fm exposes live setlist/event data behind an API key

Lyra implication:

- Lyra can build an optional "live orbit" layer:
  - upcoming shows near the user or for followed artists
  - opener/closer/encore patterns
  - live-era sequencing context
- this should remain additive, not a hard requirement for recommendation quality

Best fit:

- future provider adapters
- right rail / artist detail / companion pulse surfaces

### G. Tauri's official plugin surface supports a more complete desktop ritual

Official docs confirm:

- notification plugin works for installed apps on Windows
- global-shortcut plugin exists cross-platform
- store plugin provides persistent key-value state
- updater plugin supports signed updates, static JSON, runtime channels, and `204 No Content` for no-update responses

Lyra implication:

- native notifications can carry acquisition completion, new revelations, or provider degradation without opening the app
- global shortcuts can make Oracle, queue controls, or "reveal me something" actions feel instrument-like
- the store plugin can cleanly hold small desktop-state preferences outside ad hoc persistence
- updater matters later as part of a coherent installed-app identity, not just packaging proof

Best fit:

- future Tauri/product-depth wave, not before the current build-governance lane is settled

## 4) "Works, but..." list with solutions

1. Recommendations work, but they do not yet feel time-aware.
   Solution: add ListenBrainz fresh releases, similar-user motion, and optional event/live layers as ranked evidence, not replacements for local taste.

2. Acquisition works, but "trust in what came down" is still too implicit.
   Solution: promote AcoustID + MusicBrainz confirmation and beets normalization into visible ingest phases with reason codes.

3. Scout exists, but it is stranded outside the main recommendation and Oracle flows.
   Solution: make scout a broker provider and a visible Oracle mode with bridge-artist and scene-hop reasoning.

4. The companion works, but it does not yet feel alive.
   Solution: bind it to structured event buses for player state, recommendation provenance, acquisition motion, and provider health.

5. Lyra knows a lot about tracks, but less about moments.
   Solution: add live-event, fresh-release, and scene-tag context so recommendations can be about "now" as well as "similar."

6. UI modernization works, but it can still become ornamental if it outruns intelligence.
   Solution: every new high-traffic surface should expose rationale, provenance, timing, or ritual control.

7. Metadata enrichment works, but it is still too fragmented.
   Solution: consolidate around MBID-centric identity with Discogs as a crate-digging secondary layer.

## 5) Best next expansions after Wave 2 and Wave 3

Ordered by value-to-complexity ratio:

1. Promote AcoustID + validator + beets normalization into a visible ingest-confidence layer.
2. Expand ListenBrainz integration with fresh releases, similar users, and radio/tag endpoints.
3. Turn scout into a first-class broker/provider mode.
4. Build MBID-centric identity/art/event enrichment from MusicBrainz + Cover Art Archive.
5. Add optional live-culture adapters using Ticketmaster and setlist.fm.
6. Upgrade the companion from shell ornament to event-driven pulse surface.
7. Add selective Tauri-native ritual features:
   - notifications
   - global shortcuts
   - cleaner small-state persistence
   - updater later, once release governance is mature

## 6) Non-goals

- Do not let Lyra become a ticketing app.
- Do not let "culture pulse" become generic trends spam.
- Do not replace local emotional topology with API popularity feeds.
- Do not rebuild mature metadata tools end-to-end if bounded interop is enough.
- Do not add desktop-native features that do not strengthen ritual, trust, or continuity.

## 7) Sources

- ListenBrainz API index: https://listenbrainz.readthedocs.io/en/latest/users/api/index.html
- ListenBrainz recommendations: https://listenbrainz.readthedocs.io/en/latest/users/api/recommendation.html
- ListenBrainz core API: https://listenbrainz.readthedocs.io/en/latest/users/api/core.html
- ListenBrainz metadata API: https://listenbrainz.readthedocs.io/en/latest/users/api/metadata.html
- ListenBrainz misc / fresh releases: https://listenbrainz.readthedocs.io/en/latest/users/api/misc.html
- MusicBrainz API: https://musicbrainz.org/doc/MusicBrainz_API
- MusicBrainz rate limiting: https://musicbrainz.org/doc/Rate_Limiting
- Cover Art Archive API: https://musicbrainz.org/doc/Cover_Art_Archive/API
- Last.fm API: https://www.last.fm/api
- Last.fm `track.getSimilar`: https://www.last.fm/api/show/track.getSimilar
- Discogs developer support on search/browse: https://support.discogs.com/hc/en-us/articles/360003622014-How-To-Browse-Search-In-The-Database
- beets Discogs plugin: https://beets.readthedocs.io/en/stable/plugins/discogs.html
- beets FetchArt plugin: https://beets.readthedocs.io/page/plugins/fetchart.html
- beets MBSync plugin: https://beets.readthedocs.io/en/stable/plugins/mbsync.html
- AcoustID web service: https://acoustid.org/webservice
- Ticketmaster developer portal: https://developer.ticketmaster.com/products-and-docs/apis/getting-started/
- Ticketmaster Discovery API: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
- setlist.fm API: https://api.setlist.fm/docs/1.0/index.html
- Tauri notification plugin: https://v2.tauri.app/ko/plugin/notification/
- Tauri global shortcut plugin: https://v2.tauri.app/ko/plugin/global-shortcut/
- Tauri store plugin: https://v2.tauri.app/es/plugin/store/
- Tauri updater plugin: https://v2.tauri.app/ko/plugin/updater/
