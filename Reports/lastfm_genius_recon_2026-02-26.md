# Last.fm + Genius Recon (Pre-Implementation)

Date: 2026-02-26
Scope: Metadata enrichment before UI phase

## Current State
- Config supports `LASTFM_API_KEY` and `GENIUS_ACCESS_TOKEN`.
- No active provider modules in `oracle/enrichers/` for Last.fm or Genius.
- `oracle enrich-all` currently shells out to `scripts/enrich_genres.py` (legacy script, weak retries/error handling).

## Last.fm API Capabilities
Primary API root: `https://ws.audioscrobbler.com/2.0/`
Useful methods for this project:
- `track.getInfo`: track-level tags, listeners, playcount, wiki summary.
- `track.getTopTags`: track-level genre/mood tags.
- `artist.getTopTags`: fallback tags when track-level tags are sparse.
- `track.getSimilar`: semantic neighbors for discovery and validation.
- `artist.getSimilar`: artist graph context.

Best-use in Lyra:
- Populate `tracks.genre` + `tracks.subgenres` from top tags.
- Add popularity/listener priors for tie-breaking duplicate candidates.
- Improve cold-start recommendations when CLAP similarity is close.

## Genius API Capabilities
API root: `https://api.genius.com`
Useful endpoints:
- `GET /search`: find candidate songs by artist+title text query.
- `GET /songs/:id`: canonical metadata (artist, release date, URL, pageviews, description fields).
- `GET /artists/:id`: artist metadata.
- `GET /referents`: annotation graph (optional, expensive).

Important constraint:
- Official API is metadata-first; full licensed lyrics are not guaranteed in API payloads.

Best-use in Lyra:
- Canonical title/artist disambiguation.
- Popularity/context features (`pageviews`, release timing).
- Optional lightweight text descriptors from descriptions/annotations.

## What We Should Implement Now
1. Production-grade Last.fm provider in `oracle/enrichers/lastfm.py`:
   - strict timeouts
   - retry/backoff on 429/5xx
   - normalized tag extraction
2. Production-grade Genius provider in `oracle/enrichers/genius.py`:
   - search + candidate scoring
   - song detail fetch with retries
3. Integrate both into `oracle/enrichers/unified.py`:
   - cache payloads in `enrich_cache`
   - opportunistically fill `genre/subgenres` from Last.fm tags
4. Replace CLI `enrich-all` shell-out with native provider-based enrichment loop.

## What We Should Explicitly Skip (for now)
- Bulk annotation crawling from Genius (`referents`) during normal ingest.
- Full lyric scraping in ingest path (can be added as offline job later).
- Blocking drain/watch on enrichment network calls.

## 10-Dimension Alignment Impact
- CLAP remains primary signal for `energy,valence,tension,density,warmth,movement,space,rawness,complexity,nostalgia`.
- Last.fm/Genius data should act as metadata priors and auditing signal, not overwrite CLAP-derived vectors.
- We should monitor for calibration drift by comparing score distributions after each 500-track increment.
