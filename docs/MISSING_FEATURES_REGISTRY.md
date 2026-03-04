# 🎵 MISSING FEATURES REGISTRY
## Complete Inventory of Unbuilt Features (March 2, 2026)

**Last Updated:** March 2, 2026  
**Vision Completion:** 40% (all documented, ~60% to go)  
**Definitive Source:** Comprehensive audit of chatgpt folder + codebase analysis

---

## 📋 INDEX

1. **Foundational Gaps** (Infrastructure)
2. **Discovery & Intelligence** (Brain)
3. **Playlist & Curation** (Heart)
4. **UI/UX** (Face)
5. **Integration & Automation** (Nervous System)
6. **Data Models** (Skeleton)
7. **Priority Matrix** (Roadmap)

---

## I. FOUNDATIONAL GAPS (Infrastructure)

### 1. THE BIOGRAPHER MODULE ❌ NOT BUILT
**ID:** F-001 | **Priority:** P0 | **Complexity:** Medium | **Effort:** 12-16 hrs

**Purpose:** Humanize the library. Transform "Artist Name" → rich cultural entity with context, biography, imagery, and scene understanding.

**What it fetches:**
```
• Artist biography (formation year, origin city, key albums, breakup/reunion)
• Hi-res visual assets (logos, banners, photos from TheAudioDB)
• Scene context ("Britpop movement", "Bay Area thrash metal", "Chicago drill")
• Member timeline (who joined/left, when, why)
• Influences & influenced-by relationships
• Social media links (Bandcamp, SoundCloud, Instagram, Twitter)
• Formation story & cultural significance
```

**Data sources:**
- Wikipedia (Mediawiki API — free, no auth)
- TheAudioDB (free tier + optional API key)
- Last.fm (artist.getInfo — already integrated)
- Genius (already have token)
- MusicBrainz (already integrated)
- Discogs (already have token)

**File to create:**
```
oracle/enrichers/biographer.py

class Biographer:
    def fetch_artist_bio(self, mbid: str, artist_name: str) -> Dict:
        """Comprehensive artist biography."""
        payload = {
            "artist_name": artist_name,
            "mbid": mbid,
            "bio": "",
            "image_url": "",
            "logo_url": "",
            "formation_year": 0,
            "origin": "",
            "members": [],
            "scene": "",
            "genres": [],
            "era": "",
            "influences": [],
            "influenced": [],
            "social_links": {},
        }
        return payload
```

**Database impact:**
```sql
-- Extends enrich_cache table
INSERT INTO enrich_cache (provider, external_id, data_key, data_value)
VALUES ('biographer', 'mbid', 'artist_bio', json_data)
```

**API endpoint:**
```
POST /api/enrich/biographer
  body: { artist_name: str, mbid?: str }
  returns: { biography, images, scene_context, related_artists }
```

**Integration points:**
- On artist discovery (Scout finds bridge artist)
- On library scan (enrich all existing artists)
- Lazy-load on Artist Shrine view (see F-009)
- CLI: `oracle enrich --all --include biographer`

**Risk factors:**
- Wikipedia MediaWiki API occasional unreliability (2-3% failures)
- TheAudioDB rate limits (free tier: ~100 req/min)
- Wikipedia content quality varies by artist

---

### 2. GRAPH AUTO-BUILDER ✅ BUILT
**ID:** F-002 | **Priority:** P1 | **Complexity:** Low | **Effort:** 8-10 hrs

**Purpose:** Stop building relationships on-demand. Proactively populate the entire artist graph.

**Current state:**
- ✅ `lore.py` has `get_artist_relationships()` function
- ✅ `connections` table exists and is queryable
- ✅ `oracle/graph_builder.py` exists — `GraphBuilder` class with `build_full_graph()`, `build_incremental()`, `get_stats()`
- ⚠️ Incremental triggering on new library additions may not be wired to acquisition pipeline

**What it should do:**
```python
# File: oracle/graph_builder.py (NEW)
"""
Background relationship builder.
Runs after pipeline completion or on manual trigger.
"""

class GraphBuilder:
    def build_full_graph(self) -> None:
        """After library scan, build relationships for all artists."""
        artists = self._get_all_unique_artists()
        for artist in artists:
            try:
                connections = lore.get_artist_relationships(artist)
                self._store_connections(connections)
            except Exception:
                pass  # Skip failures, continue
    
    def build_incremental(self, days: int = 1) -> None:
        """Only build for recently added artists."""
        recent_artists = self._get_artists_added_since(days)
        for artist in recent_artists:
            connections = lore.get_artist_relationships(artist)
            self._store_connections(connections)
```

**Integration:**
- Called after `indexer.run()` in pipeline
- CLI: `oracle graph build --full` (once)
- CLI: `oracle graph build --incremental --days 1` (daily)
- Runs in background (not blocking)

**Database:** Uses existing `connections` table, just populates it

**CLI commands:**
```bash
oracle graph build --full              # Build all relationships (~30-60 mins for 2k artists)
oracle graph build --incremental       # Update recently-added artists
oracle graph status                    # Show graph stats (nodes, edges)
```

**Expected result:**
```
Relationships mapped: 847 edges
Artist nodes: 1,200+
Average degree: ~3.2 connections per artist
Graph density: ~0.0027 (sparse but complete)
```

---

### 3. CREDIT ATTRIBUTION SYSTEM ❌ NOT BUILT
**ID:** F-003 | **Priority:** P2 | **Complexity:** Low | **Effort:** 6-8 hrs

**Purpose:** Track producers, remixers, feature artists, composers separately.

**New table:**
```sql
CREATE TABLE track_credits (
    id INTEGER PRIMARY KEY,
    track_id TEXT,
    role TEXT,  -- 'producer', 'remixer', 'featured', 'composer', 'engineer'
    credited_name TEXT,
    credited_mbid TEXT,
    connection_type TEXT,  -- how they connect to primary artist
    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);
```

**Data sources:**
- MusicBrainz track relationships
- Discogs release credits
- FLAC tags (PERFORMER, PRODUCER, MIXER fields)

**Use cases:**
- "Show me all tracks produced by Rick Rubin"
- "Find Skrillex remixes"
- "Zimmer-scored soundtracks in my library"

**API endpoint:**
```
GET /api/credits/by-role?role=producer&name=Rick%20Rubin
  returns: [ { track_id, artist, title, album, year } ]

GET /api/credits/track/<track_id>
  returns: [ { role, name, mbid, connection_type } ]
```

---

## II. DISCOVERY & INTELLIGENCE

### 4. DEEP CUT DISCOVERY PROTOCOL ⚠️ PARTIALLY BUILT
**ID:** F-004 | **Priority:** P1 | **Complexity:** Medium | **Effort:** 10-14 hrs

**Current state:**
- ✅ Scout finds bridge artists
- ✅ Cross-genre hunting works
- ❌ Returns "hits" not "hidden gems"
- ❌ No obscurity filtering
- ❌ No taste-aware discovery
- ❌ No proactive gap-filling

**What it should do:**

**A. Obscurity Scoring**
```python
class DeepCut:
    def hunt_by_obscurity(
        self,
        genre: str,
        target_obscurity: float = 0.8,  # 0-1: higher = more obscure
        min_acclaim: float = 0.6,        # Quality threshold
    ) -> List[Dict]:
        """
        Find: highly acclaimed but relatively unknown tracks
        
        Metrics:
        - Acclaim: Pitchfork score, AllMusic rating, Discogs rating
        - Popularity: Last.fm scrobble count (< P25)
        - Oddness: Genre fusion rarity
        """
```

**B. Taste-Aware Discovery**
```python
def hunt_with_context(
    self,
    source_genre: str,
    target_genre: str,
    your_taste: Dict,  # dimensional profile
) -> List[Dict]:
    """
    If you like "dark punk" (valence=0.2), find "dark techno",
    NOT "bright uplifting techno"
    """
```

**C. Proactive Gap-Filling**
```python
class LibraryScanAnalyzer:
    def identify_genre_gaps(self) -> None:
        """
        After scan, analyze genre distribution.
        For each pair of genres:
            if gap_exists and not artist_in_library:
                acquisition_queue.add(bridge_artist)
        """
```

**File:** `oracle/deepcut.py`

**CLI:**
```bash
oracle deepcut hunt --genre punk --obscurity 0.8 --min-acclaim 0.6
oracle deepcut gap-fill --auto-acquire        # Populate queue with bridges
oracle deepcut taste-aware --source dark --target electronic
```

**API:**
```
GET /api/deepcut/hunt?genre=punk&min_obscurity=0.8
  returns: [ { artist, album, obscurity_score, acclaim_score, why } ]

POST /api/deepcut/gap-fill
  body: { auto_acquire: bool }
  returns: { gaps_identified, queue_populated }
```

---

### 5. PATHFINDER (Relationship Navigation) ❌ NOT BUILT
**ID:** F-005 | **Priority:** P2 | **Complexity:** Medium | **Effort:** 12-16 hrs

**Purpose:** "How did I get from Radiohead to Aphex Twin?" interactive visualization.

**API endpoints:**
```python
GET /api/pathfinder/trace
  params: { from_artist, to_artist, max_hops: 3 }
  returns: {
    path: [
      { artist, connection_type, evidence, hop }
    ],
    narrative: "Radiohead connects to Aphex Twin via..."
  }

GET /api/pathfinder/explore
  params: { artist, depth: 1-3 }
  returns: {
    center: artist,
    ring1: [ direct connections ],
    ring2: [ secondary connections ],
    descriptions: { "artist1": "co-produced album X" }
  }
```

**Connection types traced:**
- Samples ("X sampled Y")
- Collaborations ("featured on")
- Band members ("member of")
- Touring partners ("toured with")
- Influence chains ("influenced by")
- Production relationships ("produced by")

**UI component:** `desktop/renderer-app/src/features/discovery/PathfinderViz.tsx`

---

### 6. RIVALRY DETECTION (LLM-Enhanced) ❌ NOT BUILT
**ID:** F-006 | **Priority:** P3 | **Complexity:** Low | **Effort:** 6-8 hrs

**Purpose:** Infer artist rivalries from culture, not just music similarity.

**Detection methods:**
```python
class Rivals:
    def infer_from_bios(self, artist1: str, artist2: str) -> float:
        """Use LLM to detect rivalry signals in artist bios."""
    
    def infer_from_context(self, artist1: str, artist2: str) -> float:
        """Shared scene + opposing aesthetics = rivalry."""
    
    def infer_from_releases(self, artist1: str, artist2: str) -> float:
        """Albums dropped same week in same genre."""
```

**Use case:**
- "Show me the Blur vs. Oasis dynamic"
- "You listen to both sides of the Metallica/Megadeth feud"

**File:** `oracle/rivals.py`

---

## III. PLAYLIST & CURATION

### 7. PLAYLIST EXPLAINABILITY SCHEMA ✅ BUILT
**ID:** F-007 | **Priority:** P1 | **Complexity:** Medium | **Effort:** 8-12 hrs

**Gap:** `oracle/explain.py` is fully implemented — `ReasonBuilder` class with `enrich_playlist()`, `build_reasons()`, `explain_run()`, dimensional + taste + deepcut + connection reason builders. Wire up to API routes if not already.

**Schema:**
```sql
CREATE TABLE playlist_runs (
    id INTEGER PRIMARY KEY,
    uuid TEXT UNIQUE,
    prompt TEXT,
    params JSON,  -- { query, n, filters }
    created_at TIMESTAMP,
    is_saved_vibe BOOLEAN,
    vibe_name TEXT
);

CREATE TABLE playlist_tracks (
    run_id INTEGER,
    track_path TEXT,
    rank INTEGER,
    score REAL,
    reasons JSON,  -- [ { type, score, text }, ... ]
    FOREIGN KEY (run_id) REFERENCES playlist_runs(id)
);
```

**Reason types:**
```python
[
    {"type": "semantic_match", "score": 0.87, "text": "Matched query 'dark ambient'"},
    {"type": "bpm_transition", "score": 0.92, "text": "BPM 135→133 (smooth flow)"},
    {"type": "artist_affinity", "score": 0.78, "text": "Genre matches your top 10%"},
    {"type": "dimensional_anchor", "score": 0.95, "text": "High energy (0.89) matches target"},
    {"type": "connection_bridge", "score": 0.84, "text": "Collaborated with prior track's artist"}
]
```

**API endpoint:**
```
GET /api/playlist/explain/<track_id>?run_id=<uuid>
  returns: { track, reasons: [ {type, score, text} ] }
```

**Integration:** Every vibe generation must store full reason provenance

---

### 8. PLAYLUST (Automated Emotional Journeys) ✅ BUILT
**ID:** F-008 | **Priority:** P1 | **Complexity:** High | **Effort:** 24-32 hrs

**Discovery:** HALFCOCKED.EXE is the manual proof-of-concept.

**HALFCOCKED structure (manual):**
- 4-act emotional narrative
- Deep-cut research (BrooklynVegan, HHGA, Pitchfork sources)
- Genre-fluent transitions
- "Cass voice" personality per act

**What Playlust should automate:**

**A. Arc Templates**
```python
TEMPLATES = {
    "epic_journey": {
        "acts": [
            {"name": "Awakening", "duration_pct": 25, "mood": "energetic"},
            {"name": "Exploration", "duration_pct": 30, "mood": "dynamic"},
            {"name": "Peak", "duration_pct": 25, "mood": "intense"},
            {"name": "Resolution", "duration_pct": 20, "mood": "contemplative"},
        ]
    },
    "comedown": {
        "acts": [...]
    },
    "deep_dive": {
        "acts": [...]
    }
}
```

**B. Emotional Arc Sequencing**
```python
class Playlust:
    def generate(
        self,
        template: str,
        duration_hours: int,
        starting_mood: Dict,  # { energy, valence, ... }
        ending_mood: Dict,
    ) -> PlaylistRun:
        """
        1. Build emotional curve (start → end)
        2. Find tracks matching dimensional arc
        3. Arrange with BPM gradients (no jumps)
        4. Add transitions via DNA/Lore/Scout
        5. Generate narrative explanations
        6. Return PlaylistRun with full reasoning
        """
```

**C. Narrative Beat Generation**
- Each act needs opening, development, climax, transition
- Generate "Cass voice" explanations via LLM
- Store in `playlist_tracks.reasons` array

**File:** `oracle/playlust.py`

**API:**
```
POST /api/playlust/generate
  body: {
    template: "epic_journey",
    duration_hours: 6,
    starting_mood: { energy: 0.8, valence: 0.6 },
    ending_mood: { energy: 0.2, valence: 0.8 }
  }
  returns: { run_id, acts, preview_url }

GET /api/playlust/templates
  returns: [ { name, description, typical_duration, arc_preview } ]
```

---

## IV. UI/UX GAPS

### 9. ARTIST SHRINE VIEW ❌ NOT BUILT
**ID:** F-009 | **Priority:** P2 | **Complexity:** Medium | **Effort:** 14-18 hrs

**Purpose:** Rich artist profile page (cultural oracle shrine).

**Components:**
```tsx
// desktop/renderer-app/src/features/library/ArtistShrine.tsx

export function ArtistShrine({ artist }: { artist: string }) {
  return (
    <div className="shrine-container">
      {/* Banner + logo + bio */}
      <header className="shrine-header" style={{ backgroundImage: bannerUrl }}>
        <img className="logo" src={logoUrl} alt={artist} />
        <h1>{artist}</h1>
        <p className="formation">{formationYear} • {origin}</p>
        <p className="bio-excerpt">{bioExcerpt}</p>
      </header>
      
      {/* Member timeline */}
      <section className="member-timeline">
        {/* Visual: Band formation → albums → breakup → reunion */}
      </section>
      
      {/* Artist network visualization */}
      <section className="constellation-mini">
        {/* Related artists with connection types */}
      </section>
      
      {/* Library tracks */}
      <section className="library-tracks">
        {/* Filterable list with play counts, scores */}
      </section>
      
      {/* Social links */}
      <section className="external-links">
        {/* Bandcamp, Spotify, SoundCloud, Instagram */}
      </section>
    </div>
  );
}
```

**Navigation:** Clicking artist name anywhere → Shrine

**Backend:** Needs Biographer (F-001) + enriched library stats

---

### 10. CONSTELLATION LIVE DATA ⚠️ COMPONENT EXISTS, NO DATA
**ID:** F-010 | **Priority:** P1 | **Complexity:** Low | **Effort:** 8-10 hrs

**Current:**
- ✅ `ConstellationScene.tsx` renders D3/canvas graph
- ✅ Route `/oracle` loads component
- ❌ Returns mock hardcoded data

**Missing:**

**A. Backend endpoint:**
```python
GET /api/constellation
  params: { genre?, era?, connection_type?, limit: int }
  returns: {
    nodes: [ { id, label, genre, era, inLibrary, trackCount } ],
    edges: [ { source, target, type, weight } ]
  }

GET /api/constellation/filters
  returns: {
    genres: [ ... ],
    eras: [ "1960s", ... ],
    connectionTypes: [ "collaborated", "influenced", ... ]
  }
```

**B. Physics layout:**
- Current: Simple concentric rings
- Should: D3 force simulation (nodes repel, edges attract)
- Cluster by genre/era

**C. Interaction:**
- Click node → Artist Shrine
- Hover edge → tooltip (connection type + evidence)
- Filter panel checkboxes
- Focus mode (click artist → show subgraph)

**Depends on:** Graph Builder (F-002)

---

### 11. TASTE PROFILE REPORT ❌ NOT BUILT
**ID:** F-011 | **Priority:** P2 | **Complexity:** Low | **Effort:** 6-8 hrs

**Purpose:** "Your Taste vs. Global Baseline" benchmarking dashboard.

**Metrics:**
```
1. Dimensional percentiles
   "Your energy: 0.72 (87th percentile)"
   "Your valence: 0.34 (22nd percentile)"

2. Obscurity index
   "45% of library below mainstream threshold"

3. Era distribution (histogram)
   1960s (5%) | 1970s (8%) | ... | 2010s+ (16%)

4. Genre pie chart

5. Discovery velocity trend
   Line graph: tracks added/month over 12 months

6. Scene connectivity
   "Your artists: 127 connections (78th percentile)"
```

**API:**
```
GET /api/taste/profile
  returns: {
    dimensional_profile: { energy, valence, ... },
    percentiles: { energy_percentile, ... },
    obscurity_index,
    era_distribution,
    genre_distribution,
    discovery_velocity,
    connection_density
  }
```

**Component:** `desktop/renderer-app/src/features/oracle/TasteProfileCard.tsx`

---

### 12. DIMENSIONAL SEARCH SLIDERS ⚠️ PARTIALLY BUILT
**ID:** F-012 | **Priority:** P2 | **Complexity:** Low | **Effort:** 8-10 hrs

**Current:** Text-based semantic search works

**Missing:**
```tsx
// 10 sliders: 0.0 - 1.0
// energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia

// Preset filters
"Chill Evening"      → energy: 0.2-0.4, valence: 0.5-0.7
"Gym Session"        → energy: 0.8-1.0, movement: 0.8-1.0
"Late Night Coding"  → energy: 0.3-0.5, complexity: 0.6-1.0
```

**Component:** `desktop/renderer-app/src/features/search/DimensionalSearchPanel.tsx`

**Backend:** Enhance `POST /api/search` to accept dimensional filters

---

### 13. INTERACTIVE EMOTIONAL ARC EDITING ⚠️ PARTIALLY BUILT
**ID:** F-013 | **Priority:** P3 | **Complexity:** Medium | **Effort:** 12-16 hrs

**Current:** `EmotionalArcStrip.tsx` visualizes arcs (static)

**Missing:**
```tsx
// Drag-to-reorder tracks within arc
// Arc template library dropdown
// "Auto-resequence" button (keep tracks, regenerate order)
// Transition quality indicators (green/yellow/red)
// Lock track pins (always start with this)
```

---

## V. INTEGRATION & AUTOMATION

### 14. REAL-TIME PLAYBACK INTEGRATION ⚠️ PARTIALLY BUILT
**ID:** F-014 | **Priority:** P1 | **Complexity:** Medium | **Effort:** 10-14 hrs

**Current:**
- ✅ BeefWeb server running
- ✅ `taste.py` learns from signals
- ❌ Manual `oracle played` commands required

**Missing:**

**A. Automatic event consumption**
```python
# File: oracle/integrations/beefweb_bridge.py
"""
foobar2000 → BeefWeb → Lyra API webhook
Events: track_started, track_completed, track_skipped
Auto-populate playback_history table
"""
```

**B. Incremental taste updates**
- After skip → decrease affinity for dimensional profile
- After full play → increase affinity
- Ratings (thumbs up/down) → strong signal

**C. Real-time radio adaptation**
- Skip 3 high-energy tracks → Radio.chaos() lowers energy range
- Taste drift detection & profile refresh alerts

**API webhook:**
```
POST /api/playback/event
  body: {
    event_type: "track_started" | "track_completed" | "track_skipped",
    track_id,
    timestamp,
    cumulative_play_time
  }
```

---

### 15. SPOTIFY AUTOMATION ⚠️ PARTIALLY BUILT
**ID:** F-015 | **Priority:** P3 | **Complexity:** Medium | **Effort:** 10-14 hrs

**What HALFCOCKED does:**
- Creates Spotify playlists programmatically
- Uploads custom cover art per act
- Normalizes track names for matching
- Generates narrative descriptions

**What Lyra should do:**
```bash
oracle vibe export --name "Late Night" --platform spotify
# Creates Spotify playlist, uploads cover, populates description
```

**File:** `oracle/integrations/spotify_export.py`

**Dependencies:** `spotipy` (already installed)

---

## VI. DATA MODEL GAPS

### Schema additions needed:

```sql
-- Playlist explainability (F-007)
CREATE TABLE playlist_runs (
    id INTEGER PRIMARY KEY,
    uuid TEXT UNIQUE,
    prompt TEXT,
    params JSON,
    created_at TIMESTAMP,
    is_saved_vibe BOOLEAN,
    vibe_name TEXT
);

CREATE TABLE playlist_tracks (
    run_id INTEGER,
    track_path TEXT,
    rank INTEGER,
    score REAL,
    reasons JSON,
    FOREIGN KEY (run_id) REFERENCES playlist_runs(id)
);

-- Credit attribution (F-003)
CREATE TABLE track_credits (
    id INTEGER PRIMARY KEY,
    track_id TEXT,
    role TEXT,
    credited_name TEXT,
    credited_mbid TEXT,
    connection_type TEXT,
    FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

-- Playlust arc templates (F-008)
CREATE TABLE playlust_arcs (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    description TEXT,
    template JSON,
    created_at TIMESTAMP
);
```

---

## VII. PRIORITY MATRIX

### MUST-BUILD (Core Product Gaps):
1. **Biographer** (F-001) — Foundation for everything else
2. **Constellation live data** (F-010) — Flagship visual feature
3. **Playlist explainability** (F-007) — Key differentiator
4. **Graph auto-builder** (F-002) — Makes relationships proactive
5. **Deep Cut protocol** (F-004) — Core discovery innovation

### SHOULD-BUILD (High Impact):
6. **Artist Shrines** (F-009) — Showcase cultural depth
7. **Taste Profile report** (F-011) — Self-knowledge UX
8. **Real-time playback** (F-014) — Closes feedback loop
9. **Playlust MVP** (F-008) — Automates HALFCOCKED
10. **Dimensional sliders** (F-012) — Intuitive discovery

### NICE-TO-HAVE (Delight):
11. **Pathfinder** (F-005) — Interactive exploration
12. **Arc editing** (F-013) — Power user feature
13. **Rivalry detection** (F-006) — Cultural storytelling
14. **Spotify export** (F-015) — Platform integration
15. **Credit attribution** (F-003) — Producer discovery

---

## Effort Estimates Summary

| Feature | Hrs | Difficulty |
|---------|-----|-----------|
| Biographer | 12-16 | Medium |
| Graph Builder | 8-10 | Low |
| Credit Attribution | 6-8 | Low |
| Deep Cut | 10-14 | Medium |
| Pathfinder | 12-16 | Medium |
| Rivalry Detection | 6-8 | Low |
| Explainability Schema | 8-12 | Medium |
| Playlust | 24-32 | **High** |
| Artist Shrines | 14-18 | Medium |
| Constellation Live | 8-10 | Low |
| Taste Profile | 6-8 | Low |
| Dimensional Sliders | 8-10 | Low |
| Arc Editing | 12-16 | Medium |
| Playback Integration | 10-14 | Medium |
| Spotify Export | 10-14 | Medium |

**Total:** ~170-210 hours (~4-5 weeks full-time)

---

## How to Use This Registry

1. **Pick a feature by ID** (e.g., F-001)
2. **Check dependency notes** for blockers
3. **Review API/schema changes** needed
4. **Start coding** (follow file paths and patterns)
5. **Update this doc** as you complete features

**This is a living document.** Update it as you build.
