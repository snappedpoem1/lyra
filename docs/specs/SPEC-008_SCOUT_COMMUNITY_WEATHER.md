# SPEC-008 — Scout and Community Weather

**Status:** Implemented (Wave 9)
**Scope:** Backend broker expansion — two new provider slots

---

## 1. Purpose

Wave 8 made ingest trust visible. Wave 9 makes discovery time-aware and
promotes Scout from an isolated utility to a first-class recommendation provider.

This spec defines two additions to the recommendation broker:

| Provider key | Signal class | Source | Availability |
|---|---|---|---|
| `scout` | Cross-genre bridge discovery | Discogs API + local library | Acquisition leads |
| `listenbrainz_weather` | Similar-artist community top recordings | ListenBrainz API (no auth) | Library candidates + acquisition leads |

Both slots are additive: the broker continues to serve valid responses when
either provider degrades or its token/endpoint is unavailable.

---

## 2. Provider Contract (SPEC-004 extension)

Both new providers MUST return a `ProviderResult` with:

- `provider`: the provider key string (`"scout"` or `"listenbrainz_weather"`)
- `status`: `OK | DEGRADED | FAILED`
- `candidates`: list of `RecommendationCandidate` objects
- `message`: human-readable status string

Evidence types introduced by this spec:

| Evidence type | Provider | Meaning |
|---|---|---|
| `scout_bridge_artist` | `scout` | Track from a bridge artist spanning two genres |
| `scout_cross_genre` | `scout` | Discogs cross-genre fusion release |
| `community_similar_artist` | `listenbrainz_weather` | Top recording from an LB similar artist |
| `community_top_recording` | `listenbrainz_weather` | Globally top-listened recording for a similar artist |

---

## 3. Scout Provider

### 3.1 Input
- `seed_track` dict from the library (provides `genre`, `subgenres`, `artist`)
- `mode` string (`"flow"` | `"chaos"` | `"discovery"`)
- `novelty_band` string (`"safe"` | `"stretch"` | `"chaos"`)
- `limit` int
- `weight` float

### 3.2 Behavior
1. Extract `seed_genre` from `seed_track["genre"]` (or `"Unknown"` if missing)
2. Select a `bridge_genre` based on `mode`:
   - `"flow"` → genre adjacent in `_SCOUT_GENRE_BRIDGES` map
   - `"chaos"` or `"discovery"` → random pick from bridge map excluding seed genre
3. Instantiate `oracle.scout.Scout` with a fresh per-call DB connection
4. Call `Scout.cross_genre_hunt(seed_genre, bridge_genre, limit=limit)`
5. Filter `_EXCLUDED_ACQUISITION_SOURCES` (duplicates already in library)
6. Map each result to `RecommendationCandidate` with `availability=ACQUISITION_LEAD`
7. Close the Scout DB connection after use

### 3.3 Degradation
- If `DISCOGS_API_TOKEN` is not set: degrade gracefully with `DEGRADED` status
  and local-library-only results
- If Discogs API returns non-200: `DEGRADED` status, empty candidates
- If `oracle.scout` raises: `FAILED` status, logged warning, empty candidates

### 3.4 Genre Bridge Map
A static map of genres to their natural adjacent/contrast genres for seed expansion.
Defined in `oracle/recommendation_broker.py` as `_SCOUT_GENRE_BRIDGES`.

---

## 4. ListenBrainz Weather Provider

### 4.1 Purpose
Expand the existing `listenbrainz` provider with a *time-aware similar-artist chain*:
1. Resolve seed artist → MBID
2. Fetch LB similar artists for that MBID
3. For each similar artist, fetch their top recordings
4. Score by listen-count × similarity-score
5. Return as library candidates (if in library) or acquisition leads (if not)

### 4.2 New Function in `oracle/integrations/listenbrainz.py`
```python
def get_similar_artists_recordings(
    artist_name: str,
    count_artists: int = 5,
    recordings_per_artist: int = 3,
) -> list[dict]
```
Returns a list of dicts:
```python
{
  "artist": str,
  "title": str,
  "listen_count": int,
  "recording_mbid": str,
  "similarity_score": float,  # 0.0–1.0, from LB similar-artists payload
  "source_artist": str,       # the seed artist that led here
}
```

### 4.3 ListenBrainz Endpoint Used
`GET /1/similarity/artist/{artist_mbid}/` — returns `{"artist_mbid_list": [{...}], ...}`

Response shape:
```json
{
  "artist_mbid": "...",
  "similar_artists": [
    {"artist_mbid": "...", "name": "...", "similarity": 0.92},
    ...
  ]
}
```

Cache key: `similar_artists:{artist_mbid}:{count}`, TTL 7 days.

### 4.4 Degradation
- MBID resolution failure → DEGRADED, empty candidates
- LB similar-artists endpoint unavailable → DEGRADED with fallback to existing
  `_recommend_from_listenbrainz` behavior
- All 5xx errors → FAILED

---

## 5. Broker Integration

### 5.1 Weight additions
```python
DEFAULT_PROVIDER_WEIGHTS = {
    "local": 0.45,               # reduced from 0.55
    "lastfm": 0.15,              # reduced from 0.20
    "listenbrainz": 0.20,        # reduced from 0.25
    "scout": 0.10,               # new
    "listenbrainz_weather": 0.10,  # new
}
```

### 5.2 New broker functions
```python
def _recommend_from_scout(
    seed_track: dict | None,
    mode: str,
    limit: int,
    novelty_band: str,
    weight: float,
) -> ProviderResult

def _recommend_from_listenbrainz_weather(
    seed_track: dict | None,
    limit: int,
    weight: float,
) -> ProviderResult
```

### 5.3 Provider loop addition
Both functions are added to the provider loop in `recommend_tracks()`.

---

## 6. Doctor Surface

No new doctor check required. Scout and weather providers are reflected
through the existing provider health surface (`/api/recommendations/providers/health`).

---

## 7. Acceptance Criteria

- `DEFAULT_PROVIDER_WEIGHTS` contains `"scout"` and `"listenbrainz_weather"`
- `recommend_tracks()` calls both new provider functions
- Both providers degrade gracefully without breaking the response shape
- `get_similar_artists_recordings()` call succeeds with a live MBID (or empty list on outage)
- `python -m pytest -q` passes with ≥ previous count
- `docs/PROJECT_STATE.md` and `docs/PHASE_EXECUTION_COMPANION.md` reflect Wave 9 done
