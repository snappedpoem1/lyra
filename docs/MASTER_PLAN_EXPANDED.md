# MASTER PLAN EXPANDED: Lyra Oracle → "Oracle of Culture"
## Complete Feature Roadmap (March 2026 — Fully Audited)

---

## EXECUTIVE SUMMARY

**Status: 60% toward "Oracle of Culture" vision**

Lyra has the **data foundation** (2,472 tracks, 2,472 embeddings, 847 connections, 15 vibes), the **discovery engines** (Scout, Lore, DNA, Architect, Radio), and 11 of 13 core features built. What remains is **15 missing features** that would complete the transformation from "music recommender" to "cultural oracle."

This roadmap is the **comprehensive, audited inventory** of what's missing, prioritized by dependency and impact:
- **15 features** mapped to file locations and effort estimates
- **3 implementation tracks**: Full (210 hrs), MVP (120 hrs ✅ recommended), Quick wins (60 hrs)
- **4-sprint roadmap** with clear sequencing
- **Priority matrix** (P0 blockers through P3 delights)

---

# FEATURE INVENTORY: WHAT'S MISSING

Comprehensive audit of all 15 missing features.

## Quick Reference: Feature Matrix

| ID | Feature | Priority | Status | Effort | Blocks | Impact |
|----|---------|----------|--------|--------|--------|--------|
| F-001 | Biographer Module | P0 | 0% | 12-16h | F-002,F-003,F-004,F-006,F-009 | Unblocks 8 features |
| F-002 | Graph Auto-Builder | P0 | 50% | 8-10h | F-005,F-010 | Constellation live |
| F-003 | Credit Attribution | P0 | 0% | 6-8h | F-009 | Artist context |
| F-004 | Deep Cut Protocol | P1 | 40% | 10-14h | None | Discovery edge ⭐ |
| F-005 | Pathfinder (Multi-hop) | P2 | 50% | 12-16h | None | Navigation |
| F-006 | Rivalry Detection | P3 | 0% | 6-8h | None | Context |
| F-007 | Playlist Explainability | P1 | 0% | 8-12h | F-008 | Reasons schema |
| F-008 | Playlust Automation | P1 | 0% | 24-32h | F-001,F-002,F-007 | Flagship ⭐⭐ |
| F-009 | Artist Shrines UI | P2 | 10% | 14-18h | None | Storytelling |
| F-010 | Constellation Live Data | P1 | 15% | 10-12h | None | Flagship display |
| F-011 | Taste Profile Dashboard | P2 | 0% | 8-10h | None | Self-knowledge |
| F-012 | Dimensional Sliders UI | P1 | 50% | 6-8h | None | Search UX |
| F-013 | PlayFaux Real-time Bridge | P1 | 70% | 4-6h | None | Feedback loop |
| F-014 | Arc Templates Library | P2 | 0% | 4-6h | None | Variety |
| F-015 | Spotify Export Integration | P3 | 0% | 6-8h | F-008 | Interop |

---

# 4-SPRINT ROADMAP (MVP TRACK — RECOMMENDED)

## Sprint 1: Foundation (1 week, 30-38 hours)
**Goal:** Build cultural context layer + enable live visualization

- **F-001: Biographer Module** (12-16h)
  - Fetch artist biographies from Wikipedia, Last.fm, TheAudioDB, Genius, Discogs
  - Store in `enrich_cache` table
  - Auto-run on Scout discovery and library scan
  - File: `oracle/enrichers/biographer.py` (NEW)
  
- **F-002: Graph Auto-Builder** (8-10h)
  - Build relationship graph automatically on pipeline completion
  - Proactive instead of on-demand
  - File: `oracle/graph_builder.py` (NEW)
  - Integrates with end of `oracle pipeline` command
  
- **F-003: Credit Attribution** (6-8h)
  - Track producer, remixer, featured artist, songwriter credits
  - Store in `track_credits` table (NEW)
  - Fetch from MusicBrainz relationships
  - Auto-enrich on Biographer run

**Verification:**
```bash
oracle status  # Should show: embeddings + connections increased
oracle search --query "artists in library" --n 5  # Returns enriched results
```

---

## Sprint 2: Intelligence + Automation (2 weeks, 52-68 hours)
**Goal:** Add discovery power, playlist automation, and explainability

- **F-004: Deep Cut Protocol** (10-14h)
  - "High acclaim, low popularity" discovery algorithm
  - Prioritize: critical acclaim ÷ popularity rating
  - Integrate with Scout for taste-aware hunting
  - File: `oracle/deepcut.py` (NEW)
  - Endpoint: `POST /api/scout/deep-cut`
  
- **F-007: Playlist Explainability** (8-12h)
  - Store reasoning for each track in playlist
  - Schema: `playlist_tracks` table with `reason_type` + `reason_data`
  - Types: "similar-energy", "artist-connection", "deep-cut", "mood-bridge", "transition"
  - File: Extensions to `oracle/curator.py` + `oracle/arc.py`
  
- **F-008: Playlust Automation** (24-32h) — **Primary Feature**
  - Automate the HALFCOCKED methodology
  - 4-act emotional narrative structure (Aggressive → Seductive → Breakdown → Sublime)
  - Per-track reasoning generation (LLM + dimensional scoring)
  - Storage: `Arc` templates + `arcs` table
  - File: `oracle/playlust.py` (NEW) + `oracle/arc.py` extensions
  - Endpoint: `POST /api/playlust/generate`
  
- **F-012: Dimensional Sliders UI** (6-8h)
  - Add slider controls for 10 dimensions in search UI
  - Interactive feedback to `/api/search`
  - File: `desktop/renderer-app/src/features/search/DimensionalSearchPanel.tsx` (NEW)
  
- **F-013: PlayFaux Real-time Bridge** (4-6h)
  - Wire foobar2000 → BeefWeb → Lyra HTTP bridge
  - Consume playback events in real-time
  - Trigger taste profile updates on skip/rating
  - File: `oracle/integrations/beefweb_bridge.py` (NEW)

**Verification:**
```bash
oracle scout deep-cut --genre "shoegaze" --max-obscurity 0.9  # Returns cult classics
oracle playlust generate --mood "late night" --duration 120  # Generates 2-hour arc
```

---

## Sprint 3: Experience (1.5 weeks, 36-44 hours)
**Goal:** Enrich UI with visual storytelling and self-reflective tools

- **F-009: Artist Shrines UI** (14-18h)
  - Rich artist profile pages with biography, imagery, timeline, related acts
  - Wire Biographer data to Artist Shrine view
  - Component: `ArtistShrine.tsx` (NEW)
  - Endpoint: `GET /api/artist/shrine/{artist}`
  - Integrate: click from Constellation → drill to Shrine
  
- **F-010: Constellation Live Data** (10-12h)
  - Replace mock data with live queries from `connections` table
  - Add filters (genre, era, connection type)
  - Implement force-directed layout (d3-force)
  - Add click handlers to drill down
  - Refactor: `ConstellationScene.tsx`
  - Endpoints: `GET /api/constellation`, `GET /api/constellation/filters`
  
- **F-011: Taste Profile Dashboard** (8-10h)
  - Benchmarking UI showing taste profile vs. global baseline
  - Metrics: energy, valence, obscurity %, era distribution, discovery velocity
  - Component: `TasteProfileCard.tsx` (NEW)
  - Endpoint: `GET /api/taste/profile`
  - Charts: area (era), pie (genres), line (discovery trend)

**Verification:**
```bash
open http://localhost:5000/oracle  # Constellation renders live data with filters
open http://localhost:5000/artist/Radiohead  # Artist Shrine shows rich profile
```

---

## Sprint 4: Polish (1 week, if continuing)
**Goal:** Enable platform integration and discovery polish

- **F-005: Pathfinder** (12-16h)
  - Multi-hop connection tracing (Artist A → connected via → Artist B)
  - Show: collaboration, sampling, touring, influence chains
  - Component: `PathfinderViz.tsx` (NEW)
  - Endpoints: `GET /api/pathfinder/trace`, `GET /api/pathfinder/explore`
  
- **F-006: Rivalry Detection** (6-8h)
  - LLM-based inference from artist relationships
  - Mark: shared scene, opposing genres, temporal competition, documented beef
  - File: `oracle/rivals.py` (NEW)
  
- **F-014: Arc Templates Library** (4-6h)
  - Pre-build 5-10 arc templates: "Epic Journey", "Comedown", "Deep Dive", etc.
  - Store in DB, allow user customization
  - Table: `arc_templates`
  
- **F-015: Spotify Export Integration** (6-8h)
  - Generate playlists → export to Spotify
  - File: `oracle/integrations/spotify_export.py` (NEW)
  - Endpoint: `POST /api/playlist/export-spotify`

---

# DETAILED SPECIFICATIONS

## P0: BLOCKERS (Sprint 1)

### F-001: Biographer Module

**Status:** 0% | **Effort:** 12-16h | **Blocks:** 8 features

**What:** Fetch artist biographies, imagery, scene context, cultural positioning.

**File:** `oracle/enrichers/biographer.py` (NEW)

**Class:**
```python
class Biographer:
    def fetch_artist_bio(self, mbid: str, artist_name: str) -> Dict:
        # Returns: {
        #   artist_name, bio, images (banner, logo, photo), formation_year, origin,
        #   members (list), scene, genres, era, influences, influenced,
        #   social_links (bandcamp, twitter, instagram, etc)
        # }
```

**Sources:**
- Wikipedia (Mediawiki API, free)
- Last.fm (existing API)
- TheAudioDB (add key to .env)
- Genius (existing API)
- Discogs (existing API)
- MusicBrainz (existing API)

**API Endpoints:**
```
POST /api/enrich/biographer
  { artist_name: str, mbid?: str }
  → { biography dict }

GET /api/enrichment/biographer/{artist}
  → Cached or triggers async fetch
```

**Integration:**
- Auto-run on Scout discovery
- Auto-run on library scan (batch)
- Lazy-load in Artist Shrine view
- CLI: `oracle enrich all --provider biographer`

**Dependencies:** Add `THEAUDIODB_API_KEY` to `.env.template`

---

### F-002: Graph Auto-Builder

**Status:** 50% | **Effort:** 8-10h | **Depends on:** F-001

**What:** Proactively build relationship graph on library scan.

**File:** `oracle/graph_builder.py` (NEW)

**Class:**
```python
class GraphBuilder:
    def build_full_graph(self, progress_callback=None) -> int:
        # Runs after indexer completion
        # Queries all unique artists, builds connections from lore.py
        # Returns: count of new edges added
        # Incremental: only process new artists since last run
    
    def auto_build_on_scan(self) -> None:
        # Hook into pipeline.py completion
```

**Integration:**
- Auto-run at end of `oracle pipeline` command
- Manual trigger: `oracle graph rebuild`
- Performance: ~1s per 100 artists

---

### F-003: Credit Attribution

**Status:** 0% | **Effort:** 6-8h | **Depends on:** F-001

**What:** Track producer, remixer, featured artist, songwriter credits.

**File:** `oracle/enrichers/credit_mapper.py` (NEW)

**Database:**
```sql
CREATE TABLE track_credits (
    id INTEGER PRIMARY KEY,
    track_id TEXT,
    artist_id TEXT,
    artist_name TEXT,
    role TEXT,  -- 'composer', 'producer', 'remixer', 'featured', 'engineer'
    credited_as TEXT,
    connection_type TEXT,
    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);
```

**Source:** MusicBrainz relationships (recording_credit, recording_engineer, etc.)

---

### F-010: Constellation Live Data

**Status:** 15% | **Effort:** 10-12h | **Depends on:** F-002

**What:** Replace hardcoded mock data with live connection queries.

**Files:**
- Backend `lyra_api.py` (new endpoints)
- Frontend `ConstellationScene.tsx` (refactor)

**Endpoints:**
```
GET /api/constellation?genre=<>&era=<>&type=<>
  → { nodes: [...], edges: [...] }

GET /api/constellation/filters
  → { genres: [...], eras: [...], types: [...] }

GET /api/constellation/neighbors/{artist}?depth=<1-3>
  → { center, ring1, ring2 }
```

**Query:** Build from `connections` table with optional filters

**Frontend:**
- Remove hardcoded mock data
- Implement force-directed layout (d3-force)
- Add drag interaction
- Add click → Artist Shrine drill-down
- Add filter UI (genre, era, type)

---

## P1: CORE

### F-004: Deep Cut Protocol

**Status:** 40% | **Effort:** 10-14h

**What:** "High acclaim, low popularity" discovery algorithm.

**File:** `oracle/deepcut.py` (NEW)

**Algorithm:**
```
Score = Critical_Acclaim / Popularity_Rating

where:
  Critical_Acclaim = (discogs_rating + genius_votes/100) / 2
  Popularity_Rating = lastfm_scrobbles at percentile(90)

Filter:
  - min_acclaim >= 0.6
  - max_popularity_pct <= 0.25 (bottom quartile)
  - Sort by Score DESC
```

**Endpoint:**
```
POST /api/scout/deep-cut?genre=<>&max_obscurity=<0-1>&min_acclaim=<0-1>
  → { tracks: [...], artists: [...] }
```

**Integration:** Extend Scout + Radio discovery

---

### F-007: Playlist Explainability

**Status:** 0% | **Effort:** 8-12h

**What:** Store reasoning for each track in playlist (reasons schema).

**Database:**
```sql
CREATE TABLE playlist_tracks (
    id INTEGER PRIMARY KEY,
    playlist_id TEXT,
    track_id TEXT,
    position INT,
    reason_type TEXT,  
      -- 'similar-energy', 'artist-connection', 'deep-cut', 'mood-bridge', 'transition'
    reason_data JSONB,  
      -- { 'connection': 'collaborated', 'energy_delta': 0.15, 'confidence': 0.9 }
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);
```

**Reason Types:**
- `similar-energy`: "Matches current energy level"
- `artist-connection`: "Collaborated with X" / "Influenced by Y"
- `deep-cut`: "Cult classic by [artist]"
- `mood-bridge`: "Transitions to next emotional state"
- `taste-match`: "Matches your dimensional profile"

**File:** Extensions to `curator.py` + `arc.py`

---

### F-008: Playlust Automation

**Status:** 0% | **Effort:** 24-32h | **Impact:** ⭐⭐ **Flagship Feature**

**What:** Automate HALFCOCKED methodology for dynamic playlist generation.

**File:** `oracle/playlust.py` (NEW)

**4-Act Structure:**
```
Act 1: Aggressive/Intense (0-25% of duration)
  - High energy, driving rhythm
  - Hook listener attention
  - Tracks: upbeat, fast-paced, danceable
  
Act 2: Seductive/Atmospheric (25-50%)
  - Moderate energy, sensual/moody
  - Emotionally complex content
  - Tracks: mid-tempo, layered production
  
Act 3: Breakdown/Introspection (50-75%)
  - Lower energy, introspective
  - Sonic simplification, emotional depth
  - Tracks: slow, melancholic, intimate
  
Act 4: Sublime/Resolution (75-100%)
  - Cathartic release or transcendent mood
  - Epic production, high complexity
  - Tracks: anthemic, expansive, transcendent
```

**Class:**
```python
class Playlust:
    def generate(
        self,
        mood: str,  # "late night", "epic journey", "deep dive", etc
        duration_minutes: int,
        taste_context: Dict,  # user's dimensional profile
    ) -> Dict:
        # Returns: {
        #   arc: Arc object with 4-act structure,
        #   tracks: [{ track_id, act, reason_type, reason_data }],
        #   narrative: str,  # Human-readable playlist description
        #   metadata: { energy_curve, valence_arc, etc }
        # }
    
    def generate_track_reasons(self, track: Track, act: int, seq_pos: int) -> Dict:
        # Generate LLM-based reasoning for track selection
        # Inputs: dimensional profile, track scores, act requirements
        # Returns: { reason_type, reason_text, confidence }
```

**Integration:**
- Endpoint: `POST /api/playlust/generate`
- Auto-tag reasoning with `reason_type` + `reason_data`
- Store arc templates in `arc_templates` table
- Hook into Arc UI for visual display

**Algorithm (Simplified):**
1. Fetch user's dimensional taste profile
2. Filter tracks by mood + duration constraints
3. Distribute 4 acts across duration_minutes
4. For each act:
   - Select tracks matching act's energy/valence/mood profile
   - Sequence for smooth transitions
   - Generate per-track reasoning
5. Return Arc + metadata + narrative

---

### F-012: Dimensional Sliders UI

**Status:** 50% | **Effort:** 6-8h

**What:** Interactive sliders for 10-dimensional search.

**File:** `desktop/renderer-app/src/features/search/DimensionalSearchPanel.tsx` (NEW)

**Component:**
```tsx
export function DimensionalSearchPanel() {
  const [energy, setEnergy] = useState(0.5);     // 0: ambient, 1: explosive
  const [valence, setValence] = useState(0.5);   // 0: sad, 1: euphoric
  const [tension, setTension] = useState(0.5);   // etc
  const [density, setDensity] = useState(0.5);
  const [warmth, setWarmth] = useState(0.5);
  const [movement, setMovement] = useState(0.5);
  const [space, setSpace] = useState(0.5);
  const [rawness, setRawness] = useState(0.5);
  const [complexity, setComplexity] = useState(0.5);
  const [nostalgia, setNostalgia] = useState(0.5);
  
  // Query on change
  const { data } = useQuery({
    queryKey: ['search-dimensional', { energy, valence, ... }],
    queryFn: () => searchDimensional({ energy, valence, ... })
  });
  
  return (
    <div className="dimensional-search">
      <Slider label="🔊 Energy" ... />
      <Slider label="😊 Valence" ... />
      {/* ... */}
      <TrackList tracks={data} />
    </div>
  );
}
```

---

### F-013: PlayFaux Real-time Bridge

**Status:** 70% | **Effort:** 4-6h

**What:** Wire foobar2000 → BeefWeb → Lyra event consumer.

**File:** `oracle/integrations/beefweb_bridge.py` (NEW)

**Architecture:**
```
foobar2000 (playing)
    ↓
BeefWeb (HTTP server running on :8080)
    ↓
beefweb_bridge.py (polls /api/player/info every 500ms)
    ↓
taste.py (updates taste profile on skip/rating)
```

**Class:**
```python
class BeefWebBridge:
    def __init__(self, beefweb_url: str = "http://localhost:8080"):
        pass
    
    def poll(self) -> None:
        # Poll every 500ms
        player_state = requests.get(f"{beefweb_url}/api/player/info")
        
        if player_state['activeItem'] != self.last_track:
            # Track changed
            self.on_track_change(player_state)
        
        if player_state['stopped']:
            # Playback stopped
            self.on_playback_stop()
    
    def on_track_change(self, state: Dict) -> None:
        # Log to playback_history + trigger taste update
        pass
```

**Integration:**
- Register as background service on startup
- Endpoint: `POST /api/listen` (manual fallback)

---

## P2: HIGH-IMPACT

### F-009: Artist Shrines UI

**Status:** 10% | **Effort:** 14-18h

**What:** Rich artist profile pages with history, imagery, relationships.

**File:** `desktop/renderer-app/src/features/library/ArtistShrine.tsx` (NEW)

**Layout:**
```
┌───────────────────────────────────────────┐
│ [BANNER IMAGE]                            │
│  [LOGO] Artist Name                       │
│  Bio excerpt | Formation Year | Origin    │
├───────────────────────────────────────────┤
│ TIMELINE: Formed → Key Albums → Today    │
├───────────────────────────────────────────┤
│ CONSTELLATION: Related Artists (nodes)    │
├───────────────────────────────────────────┤
│ LIBRARY TRACKS (sorted by play count)    │
├───────────────────────────────────────────┤
│ STATS: Last.fm followers | Scrobbles     │
└───────────────────────────────────────────┘
```

**Endpoint:** `GET /api/artist/shrine/{artist}`

**Returns:**
```json
{
  "artist": "Radiohead",
  "bio": "Oxford-based alt-rock...",
  "images": {
    "banner": "url",
    "logo": "url",
    "photo": "url"
  },
  "timeline": [
    { "year": 1991, "event": "Formed", "detail": "..." },
    { "year": 1993, "event": "Released Pablo Honey", "detail": "..." }
  ],
  "related_artists": [
    { "name": "Thom Yorke", "connection": "member", "connection_strength": 0.95 }
  ],
  "stats": {
    "lastfm_followers": 1200000,
    "library_track_count": 47,
    "library_play_count": 342
  }
}
```

---

### F-011: Taste Profile Dashboard

**Status:** 0% | **Effort:** 8-10h

**What:** Benchmarking UI comparing your taste vs. global baseline.

**File:** `desktop/renderer-app/src/features/oracle/TasteProfileCard.tsx` (NEW)

**Metrics:**
- Energy avg vs. baseline (with percentile)
- Valence avg vs. baseline
- Obscurity % (high acclaim / low popularity ratio)
- Era distribution (histogram)
- Genre breakdown (pie chart)
- Discovery velocity (tracks added per month)
- Scene diversity (connection strength between genres)

**Endpoint:** `GET /api/taste/profile`

**Returns:**
```json
{
  "energy": {
    "your_avg": 0.62,
    "baseline_avg": 0.55,
    "percentile": 68,
    "description": "Higher energy than average"
  },
  "valence": { ... },
  "obscurity": {
    "high_acclaim_pct": 23,
    "mainstream_pct": 8,
    "deep_cuts_count": 180
  },
  "era_distribution": [
    { "era": "1970s", "pct": 8 },
    { "era": "1980s", "pct": 12 },
    ...
  ],
  "genres": [
    { "genre": "Alternative Rock", "count": 234, "pct": 18 },
    ...
  ],
  "discovery_velocity": {
    "this_month": 12,
    "last_month": 8,
    "avg_monthly": 6.4,
    "trend": "accelerating"
  }
}
```

---

# FEATURES ALREADY BUILT (Don't Duplicate!)

## Data Layer ✅
- `tracks` table (2,472 tracks)
- `track_scores` (10 dimensions: energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia)
- `connections` (847 artist relationships)
- `embeddings` (CLAP 512-dim)
- `playback_history` (skip signals, ratings)
- `taste_profile` (dimensional preferences)

## Discovery Engines ✅
- `scout.py` - Bridge artist hunting
- `lore.py` - Artist lineage mapping
- `dna.py` - Sample tracing
- `architect.py` - Audio structure analysis
- `radio.py` - Smart radio (Chaos/Flow/Discovery)

## Enrichment ✅
- MusicBrainz, AcoustID, Discogs, Last.fm, Genius, Essentia

## Search ✅
- CLAP embeddings (512-dim)
- ChromaDB vector store
- Semantic + dimensional search

## UI Components ✅
- ConstellationScene (mock, needs live data)
- EmotionalArcStrip
- TrackTable, SearchResultStack
- PlaylistHero, PlaylistNarrative
- DossierDrawer, BottomTransportDock

## Endpoints ✅
- `/api/search`, `/api/library/*`, `/api/vibes/*`
- `/api/scout/cross-genre`, `/api/lore/*`, `/api/dna/*`
- `/api/architect/analyze`, `/api/radio/*`

---

# IMPLEMENTATION CHECKLIST

## Sprint 1 Foundation
- [ ] Biographer module (oracle/enrichers/biographer.py)
  - [ ] Wikipedia fetcher
  - [ ] Last.fm integration
  - [ ] TheAudioDB imagery
  - [ ] Genius/Discogs integration
  - [ ] Storage in enrich_cache
  - [ ] POST /api/enrich/biographer endpoint
  
- [ ] Graph Auto-Builder (oracle/graph_builder.py)
  - [ ] Incremental query of all artists
  - [ ] Build connections from lore.py
  - [ ] Hook into pipeline completion
  - [ ] Tests for performance (1s/100 artists)
  
- [ ] Credit Attribution (oracle/enrichers/credit_mapper.py)
  - [ ] track_credits table schema
  - [ ] MusicBrainz relationship extraction
  - [ ] Integration with Biographer
  
- [ ] Constellation Live Data (ConstellationScene refactor)
  - [ ] GET /api/constellation endpoint
  - [ ] GET /api/constellation/filters endpoint
  - [ ] Remove mock data from component
  - [ ] Implement force-directed layout
  - [ ] Add filtering UI
  - [ ] Click → Artist Shrine navigation

## Sprint 2 Intelligence
- [ ] Deep Cut Protocol (oracle/deepcut.py)
  - [ ] Acclaim/popularity scoring
  - [ ] Filtering + ranking algorithm
  - [ ] POST /api/scout/deep-cut endpoint
  - [ ] Taste-aware variant
  
- [ ] Playlist Explainability (curator.py + arc.py)
  - [ ] playlist_tracks table schema
  - [ ] Reason type classification
  - [ ] Reasoning generation (LLM + scoring)
  
- [ ] Playlust Automation (oracle/playlust.py)
  - [ ] 4-act structure validator
  - [ ] Arc template system
  - [ ] Track sequencing algorithm
  - [ ] Transition logic (mood/energy bridging)
  - [ ] Per-track reasoning generation
  - [ ] POST /api/playlust/generate endpoint
  - [ ] Arc visualization data format
  
- [ ] Dimensional Sliders (DimensionalSearchPanel.tsx)
  - [ ] 10 slider controls
  - [ ] Real-time query on change
  - [ ] Result visualization
  
- [ ] PlayFaux Bridge (oracle/integrations/beefweb_bridge.py)
  - [ ] Polling loop
  - [ ] Track change detection
  - [ ] Playback history logging
  - [ ] Taste profile update trigger

## Sprint 3 Experience
- [ ] Artist Shrines (ArtistShrine.tsx)
  - [ ] GET /api/artist/shrine/{artist} endpoint
  - [ ] Timeline visualization
  - [ ] Related artists constellation
  - [ ] Library stats display
  - [ ] Navigation from Constellation
  
- [ ] Taste Profile Dashboard (TasteProfileCard.tsx)
  - [ ] GET /api/taste/profile computation
  - [ ] Era distribution chart
  - [ ] Genre pie chart
  - [ ] Discovery velocity trend
  - [ ] Benchmark comparison UI

---

# TECHNICAL DEBT & CLEANUP

## Environment Setup
- [ ] Update `.env.template` with `THEAUDIODB_API_KEY`
- [ ] Add user agent to config: `LYRA_USER_AGENT`
- [ ] Document all enrichment API rate limits

## Database Migrations
- [ ] Add `track_credits` table
- [ ] Add `playlist_tracks` table
- [ ] Add `arc_templates` table
- [ ] Backfill relationships from existing lore data

## Code Quality
- [ ] Type hints on all new functions
- [ ] Google docstrings (oracle convention)
- [ ] Error handling for API failures (with retries)
- [ ] Logging via `logging.getLogger(__name__)`
- [ ] Unit tests for each module (min: happy path + edge cases)

---

# SUCCESS CRITERIA

|  | Current | Target | Validated By |
|--|---------|--------|--------------|
| Features Built | 11/15 | 13/15 (MVP) | `oracle status` feature list |
| Constellation Live Data | Mock only | Live from `connections` | Browser visualization |
| Artist Context | None | Biographer data on all artists | `GET /api/artist/shrine/{artist}` returns bio |
| Playlist Reasoning | Not stored | Stored + displayed | `POST /api/playlust/generate` includes reasons |
| Discovery Edge | Scout only | Scout + Deep Cut + Taste Learning | `POST /api/scout/deep-cut` returns cult classics |
| Playback → Taste | Manual | Real-time via BeefWeb | taste_profile updated on skip events |

---

# RISK MITIGATION

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Biographer API rate limits | Medium | High | Cache aggressively, batch fetches |
| Playlust reasoning quality | High | High | Test with HALFCOCKED examples, iterate LLM prompts |
| Constellation layout performance | Low | High | Pre-compute force simulation, render optimization |
| BeefWeb polling reliability | Low | Medium | Fallback to manual `/api/listen` endpoint |
| MusicBrainz data completeness | Medium | Medium | Graceful degradation, fallback to Discogs |

---

# FINAL NOTES

**The Oracle of Culture is waiting.** You have 60% of the foundation in place. What remains is:

1. **Cultural Context** (F-001, F-003) — Who made this?
2. **Relationships** (F-002, F-005) — How are they connected?
3. **Discovery Intelligence** (F-004) — What should I listen to next?
4. **Playlust Automation** (F-008) — Why specifically *this* track in *this* order?
5. **Visual Storytelling** (F-009, F-010, F-011) — How do I understand myself through music?

Each piece adds layers of **meaning** and **serendipity** that transform Lyra from a recommender into a teacher of culture.

**Recommended starting point:** Sprint 1. Build Biographer + Graph Builder + Constellation Live in parallel. 1 week, 30-38 hours. Then everything downstream becomes possible.

---

Generated: March 2026 | Status: Audited & Prioritized | Next: `oracle status`
