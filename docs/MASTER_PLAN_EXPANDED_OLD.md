# MASTER PLAN EXPANDED: Lyra Oracle → "Oracle of Culture"
## Complete Feature Roadmap (March 2026 — Fully Audited)

---

## EXECUTIVE SUMMARY

**Status: 60% toward "Oracle of Culture" vision**

Lyra has the **data foundation** (2,472 tracks, 2,472 embeddings, 847 connections, 15 vibes), the **discovery engines** (Scout, Lore, DNA, Architect, Radio), and 11 of 13 core features built. What remains is **15 missing features** that would complete the transformation from "music recommender" to "cultural oracle."

This roadmap is the **comprehensive, audited inventory** of what's missing, prioritized by dependency and impact. It includes:
- **15 features** mapped to file locations and effort estimates
- **3 implementation tracks**: Full (210 hrs), MVP (120 hrs ✅ recommended), Quick wins (60 hrs)
- **4-sprint roadmap** with clear sequencing
- **Priority matrix** (P0 blockers through P3 delights)

---

# FEATURE INVENTORY: WHAT'S MISSING

Comprehensive audit of all 15 missing features, organized by priority and implementation difficulty.

## Quick Reference: Feature Matrix

| ID | Feature | Priority | Status | Effort | Dependencies | Impact |
|----|---------|----------|--------|--------|--------------|--------|
| F-001 | Biographer Module | P0 | 0% | 12-16h | None | Unblocks 8 features |
| F-002 | Graph Auto-Builder | P1 | 50% | 8-10h | Biographer | Constellation live data |
| F-003 | Credit Attribution | P1 | 0% | 6-8h | Biographer | Artist Shrines |
| F-004 | Deep Cut Protocol | P1 | 40% | 10-14h | Biographer | Discovery edge |
| F-005 | Pathfinder (Multi-hop) | P2 | 50% | 12-16h | Graph Builder | Navigation UI |
| F-006 | Rivalry Detection | P3 | 0% | 6-8h | Biographer | Discovery context |
| F-007 | Playlist Explainability | P1 | 0% | 8-12h | Track scores | Reasons schema |
| F-008 | Playlust Automation | P1 | 0% | 24-32h | All of Sprint 1-3 | Flagship feature ⭐ |
| F-009 | Artist Shrines UI | P2 | 10% | 14-18h | Biographer, Graph | Cultural storytelling |
| F-010 | Constellation Live Data | P1 | 15% | 10-12h | Graph Builder | Flagship display |
| F-011 | Taste Profile Benchmarking | P2 | 0% | 8-10h | Track scores | Self-knowledge |
| F-012 | Dimensional Sliders UI | P1 | 50% | 6-8h | Dimensional scoring | Search UX |
| F-013 | PlayFaux Real-time Bridge | P1 | 70% | 4-6h | Playback history | Taste feedback loop |
| F-014 | Arc Templates Library | P2 | 0% | 4-6h | Arc engine | Playlist sequencing |
| F-015 | Spotify Export Integration | P3 | 0% | 6-8h | Playlust, Playlist UI | Platform interop |

---

## PRIORITY PYRAMID

```
┌─────────────────────────────────────────────────────────────┐
│  P0: BLOCKERS (Must build first)                            │
│  • Biographer (F-001): Required by 8 other features         │
│  • Graph Auto-Builder (F-002): Enables Constellation        │
│  • Constellation Live (F-010): Flagship visual              │
│  Effort: 30-38 hours | Timeline: 1 week                     │
├─────────────────────────────────────────────────────────────┤
│  P1: CORE (Should build next)                               │
│  • Deep Cut Protocol (F-004): Discovery differentiator      │
│  • Playlist Explainability (F-007): Reasons schema          │
│  • Playlust Automation (F-008): Heaviest but multiplier ⭐  │
│  • Dimensional Sliders (F-012): Search UX                   │
│  • PlayFaux Integration (F-013): Feedback loop              │
│  Effort: 52-68 hours | Timeline: 2-3 weeks                 │
├─────────────────────────────────────────────────────────────┤
│  P2: HIGH-IMPACT (Build if time permits)                    │
│  • Artist Shrines (F-009): Visual & cultural depth          │
│  • Pathfinder (F-005): Navigation layer                     │
│  • Taste Profile (F-011): Self-reflection dashboard         │
│  • Arc Templates (F-014): Playlist variety                  │
│  Effort: 36-44 hours | Timeline: 1.5-2 weeks               │
├─────────────────────────────────────────────────────────────┤
│  P3: DELIGHT (Polish & scale)                               │
│  • Rivalry Detection (F-006): Context enrichment            │
│  • Spotify Export (F-015): Platform interop                 │
│  Effort: 12-16 hours | Timeline: 1 week                     │
└─────────────────────────────────────────────────────────────┘
```

---

## IMPLEMENTATION OPTIONS

### Option A: Full Build (210 hours, 5-7 weeks, 1 engineer)
**All 15 features → Complete "Oracle of Culture"**
- Sprint 1: F-001, F-002, F-003, F-010 (Biographer + Graph + Constellation)
- Sprint 2: F-004, F-007, F-009, F-011, F-012, F-013 (Discovery + Polish + UI)
- Sprint 3: F-005, F-008, F-014 (Pathfinder + Playlust + Templates)
- Sprint 4: F-006, F-015 (Rivalry + Export, cleanup)

### Option B: MVP Track (120 hours, 2-3 weeks, 1 engineer) ✅ **RECOMMENDED**
**Core features for cultural oracle → Maximum value per hour**
- Sprint 1: F-001, F-002, F-003, F-010 (Foundation)
- Sprint 2: F-004, F-008, F-007 (Discovery + Automation + Reasons)
- Sprint 3: F-009, F-011, F-012 (UX Polish)

### Option C: Quick Wins (60 hours, 1-2 weeks, 1 engineer)
**High-impact, low-complexity features → Rapid feedback loop**
- Sprint 1: F-001, F-010 (Biographer + Constellation) — 22-28h
- Sprint 2: F-012, F-013, F-014 (UI tweaks + Playback integration) — 14-20h
- Sprint 3: F-004 (Deep Cut hunt) — 10-14h

---

# DETAILED FEATURE SPECIFICATIONS

## P0: BLOCKERS

### F-001: Biographer Module

**Status:** 0% | **Priority:** P0 | **Effort:** 12-16h | **Blocks:** 8 features

**What:** Fetch artist biographies, imagery, scene context, and cultural positioning from Wikipedia, Last.fm, TheAudioDB, Genius, Discogs, MusicBrainz.

**File:** `oracle/enrichers/biographer.py` (NEW)

**Signature:**
```python
class Biographer:
    def fetch_artist_bio(self, mbid: str, artist_name: str) -> Dict:
        # Returns: bio, images, logo, formation_year, origin, members, 
        #          scene, genres, era, influences, influenced, social_links
```

**Endpoints:**
```
POST /api/enrich/biographer
  { artist_name: str, mbid?: str } → biography dict
  
GET /api/enrichment/biographer/{artist}  
  Returns cached biography or triggers async fetch
```

**Integration:**
- Auto-run on Scout discovery of bridge artist
- Auto-run on library scan (batch)
- Lazy-load in Artist Shrine view
- Enable/disable via CLI: `oracle enrich all --provider biographer`

**Dependencies:**
- ✅ Last.fm API (existing)
- ✅ Genius API (existing)
- ✅ MusicBrainz (existing)
- ✅ Discogs API (existing)
- ⚠️ TheAudioDB API (add to `.env.template`)
- ⚠️ Wikipedia Mediawiki API (free, no auth)

**Storage:** `enrich_cache` table (provider='biographer', expires_at=now+30d)

**Validation:** Requires artist_name + (mbid OR discogs_url) for disambiguation


### 1.2 Deep Enrichment Mode: Activate Relationship Graph ⚠️ PARTIALLY BUILT

**Status:** 50% complete | **Priority:** P1 (core intelligence)

**What's built:**
- ✅ `connections` table in schema (stores artist relationships)
- ✅ `lore.py` - Historian module (maps artist lineage, band member history, collaborations)
- ✅ `POST /api/lore/trace` endpoint (traces artist relationships)
- ✅ `GET /api/lore/connections` endpoint (retrieves stored connections)
- ✅ MusicBrainz relationship extraction (member-of, collaborated-with, etc.)

**What's missing:**
- ❌ No **proactive relationship building** on library scan (relationships only built on-demand via `/api/lore/trace`)
- ❌ **Relationship strength weighting** is basic (confidence scoring not implemented)
- ❌ **Rivalry detection** (LLM-based) is mentioned but not integrated
- ❌ No **credit attribution** mapping (producers, remixers, featured artists not tracked)
- ❌ **Sample lineage verification** (DNA module has structure but no auto-verification)

**Build next:**

1. **Auto-build relationship graph on library scan** (like indexer runs automatically):
   ```python
   # oracle/graph_builder.py (NEW FILE)
   """
   Background relationship builder - runs on pipeline completion.
   Queries all artists in library and builds connection graph.
   """
   
   class GraphBuilder:
       def build_full_graph(self) -> None:
           """Run after library scan completes."""
           artists = self._get_all_unique_artists()
           for artist in artists:
               connections = lore.get_artist_relationships(artist)
               self._store_connections(connections)
   ```

2. **Add credit attribution table:**
   ```sql
   CREATE TABLE IF NOT EXISTS track_credits (
       id INTEGER PRIMARY KEY,
       track_id TEXT,
       role TEXT,  -- 'composer', 'producer', 'remixer', 'featured'
       credited_name TEXT,
       credited_mbid TEXT,
       connection_type TEXT,  -- how they connect to primary artist
       FOREIGN KEY (track_id) REFERENCES tracks(track_id)
   );
   ```

3. **Implement rivalry detection** (use LLM to infer from relationships):
   ```python
   def infer_rivalry(artist1: str, artist2: str) -> Dict:
       """
       Use LLM to detect rivalry from:
       - Shared scene but opposing genres (punk vs. metal)
       - Temporal competition (both peaked 1990s)
       - Historical beef (documented in bios)
       """
   ```

4. **Auto-verify sample lineage** (DNA module enhancement):
   - On ingress, use acoustic fingerprinting + API lookups
   - Mark as "verified", "probable", or "unconfirmed"
   - Link to `sample_lineage` table


### 1.3 Inject & Activate API Keys ✅ MOSTLY DONE

**Status:** 85% complete | **Priority:** P1 (unblocks all enrichment)

**What's in `.env` already:**
- ✅ `LASTFM_API_KEY` (used by `lastfm.py`)
- ✅ `GENIUS_TOKEN` (used by `genius.py`)
- ✅ `DISCOGS_API_TOKEN` (used by `discogs.py`)
- ✅ `MUSICBRAINZ_API` (implicit, no key needed)

**What's missing:**
- ❌ `THEAUDIODB_API_KEY` - needed for Biographer imagery
  - Free tier available at https://www.theaudiodb.com/api/v1/json/artist.php
  - No key needed for basic calls, but should add to `.env` template for clarity
  
- ❌ `WIKIPEDIA_USER_AGENT` - optional but good practice
  - Should add: `LYRA_USER_AGENT=LyraOracle/2.0 (github.com/lyra-oracle)`

**Action:** Update `.env.template`:
```bash
# === Enrichment APIs ===
LASTFM_API_KEY=your_api_key_here
THEAUDIODB_API_KEY=free_or_your_key
GENIUS_TOKEN=your_genius_api_key
DISCOGS_API_TOKEN=your_discogs_token
LYRA_USER_AGENT=LyraOracle/2.0 (github.com/lyra-oracle)
```

---

---

# PHASE 2: BROADEN HORIZONS ENGINE (Discovery Layer)

## Current State: 45% Complete
Scout exists and finds bridge artists. But it's **reactive** (called manually), not **proactive** (running continuously). Deep Cut protocol is envisioned but not built.

### 2.1 Deploy Scout in Discovery Mode (Deep Cut Protocol) ⚠️ PARTIALLY BUILT

**Status:** 40% complete | **Priority:** P1 (core discovery)

**What's built:**
- ✅ `scout.py` - Cross-genre fusion discovery engine
- ✅ `cross_genre_hunt()` method (finds bridge artists between two genres)
- ✅ Discogs integration for release discovery
- ✅ `POST /api/scout/cross-genre` endpoint
- ✅ Remix/mashup filtering

**What's missing:**
- ❌ **"Deep Cut" prioritization** - currently returns "hits", not "cult classics"
  - Should prioritize: **High Critical Acclaim / Low Popularity / High Oddness**
  - Needs: scrobble counts (Last.fm), ratings (Discogs/Genius), rarity scoring

- ❌ **Proactive hunting** - Scanner should auto-identify genre gaps and populate acquisition queue
  - Example: Library has [Punk] and [EDM] but no bridge artists → auto-hunt for Prodigy, Pendulum, etc.

- ❌ **Listener taste context** - doesn't know what *you* like in each genre
  - Should profile your taste in Punk, then recommend Punk-influenced EDM, not just any fusion

- ❌ **"Taste edge" discovery** - finding artists at the outer boundary of what you listen to
  - Example: You like Post-Rock but haven't found Godspeed You! Black Emperor → scout should surface it

**Build next:**

1. **Deep Cut Protocol implementation:**
   ```python
   # oracle/deepcut.py (NEW FILE)
   """
   "High acclaim, low popularity" discovery.
   Finds the cultured, overlooked masterpieces.
   """
   
   class DeepCut:
       def hunt_by_obscurity(
           self,
           genre: str,
           target_obscurity: float = 0.8,  # 0-1: higher = more obscure
           min_acclaim: float = 0.6,        # 0-1: quality threshold
       ) -> List[Dict]:
           """
           Search for tracks that are:
           - Highly acclaimed (Pitchfork score, Last.fm rating > threshold)
           - Relatively unknown (scrobble count < percentile P25)
           - In the target genre or nearby fusion space
           """
           # Fetch from Discogs: genre + sort by rating
           # Filter by: rating > min_acclaim
           # Filter by: scrobble_count < percentile(25)
           # Return sorted by rating DESC
   ```

2. **Taste-aware discovery:**
   ```python
   class ScoutWithTaste:
       def hunt_with_context(
           self,
           source_genre: str,
           target_genre: str,
           your_taste: Dict,  # your dimensional profile in source_genre
       ) -> List[Dict]:
           """
           Hunt for bridge artists that bridge YOUR taste flavor.
           E.g., if you like "dark punk" (valence=0.2), find "dark techno" (not bright techno).
           """
   ```

3. **Proactive gap-filling** (integrate with scanner):
   ```python
   class LibraryScanAnalyzer:
       def identify_genre_gaps(self) -> List[Dict]:
           """
           After library scan, analyze genre distribution.
           For each pair of genres with > N tracks each:
               bridge_artists = scout.cross_genre_hunt(genre1, genre2)
               if not any(artist in library):
                   acquisition_queue.add(bridge_artist)
           """
   ```

### 2.2 Implement "Pathfinder" Logic (Trace Connections) ⚠️ PARTIALLY BUILT

**Status:** 50% complete | **Priority:** P2 (nice-to-have)

**What's built:**
- ✅ `lore.py` - Artist lineage mapping
- ✅ Sample tracing (`dna.py`)
- ✅ `POST /api/lore/trace` endpoint (generates artist graph)

**What's missing:**
- ❌ **Interactive "How did I get here?" visualization**
  - Should show: Your Favorite Artist → [connected via] → New Discovery
  - Path types: samples, collaborations, band members, shared producers, touring partners, influence chains

- ❌ **Pivot functionality** (jump to related artist from now-playing)
  - From Radiohead → pivot to Thom Yorke solo → pivot to On the Beach (influenced) → etc.

- ❌ **Sample provenance drill-down**
  - "This track samples X"
  - "X was sampled by Y"
  - "Y toured with Z"
  - Creates multi-hop lineage chains

**API endpoint to add:**
```
GET /api/pathfinder/trace
  params: { from_artist, to_artist, max_hops: int }
  returns: {
    path: [
      {
        artist: str,
        connection_type: "collaboration" | "member-of" | "influenced-by" | "samples" | "toured-with",
        evidence: str,
        hop: int,
      }
    ],
    description: str,  # Human-readable narrative
  }

GET /api/pathfinder/explore
  params: { artist, depth: 1-3 }
  returns: {
    center: artist,
    ring1: related_artists (direct connections),
    ring2: secondary_connections,
    descriptions: { "artist1": "co-produced" },
  }
```

### 2.3 Enable "Taste Learning" from Playback ✅ PARTIALLY BUILT

**Status:** 60% complete | **Priority:** P1 (core feedback)

**What's built:**
- ✅ `playback_history` table (stores: track_id, ts, skipped, rating)
- ✅ `taste.py` - Taste profile learning module
- ✅ Dimensional scoring (energy, valence, warmth, etc. in `track_scores`)
- ✅ Radio engine with context awareness

**What's missing:**
- ❌ **Real-time playback integration with foobar2000**
  - Currently: Manual `oracle played --artist X --title Y` commands
  - Should be: Automatic via BeefWeb bridge (server running but not consuming signals)

- ❌ **Incremental taste profile updates**
  - Currently: Taste profile is static baseline
  - Should be: Updated after every skip/rating event

- ❌ **Collaborative filtering** (learn from similar listeners)
  - Could integrate with Last.fm's "similar users" data

**Action:** Wire foobar2000 → BeefWeb → Lyra HTTP bridge (ingest playback events).

---

---

# PHASE 3: THE "COCKPIT" EXPERIENCE (UI Layer)

## Current State: 20% Complete
Component scaffolding exists (ConstellationScene, EmotionalArcStrip), but most are **connected to mock data**, not live backend queries.

### 3.1 Populate Artist "Shrines" ❌ CONCEPT ONLY

**Status:** 10% complete | **Priority:** P2 (high impact visually)

**What should happen when you click an artist:**
1. Load rich profile page with:
   - ✅ Track count, album list (exists in `/api/library/artists/{artist}`)
   - ❌ **Artist bio** (from Biographer module → not yet built)
   - ❌ **High-res banner + logo** (from TheAudioDB)
   - ❌ **Related acts network** (from connections table, needs UI)
   - ❌ **Timeline of influence** (members, collaborations, samples)
   - ❌ **Social/listening stats** (Last.fm followers, scrobbles)

**Current state:**
- `getLibraryArtistDetail()` returns track list only
- No biography, images, or relationship visualization

**Build next:**

1. **Extend `libraryArtistDetailSchema` to include enrichment:**
   ```typescript
   // desktop/renderer-app/src/services/lyraGateway/queries.ts
   
   export async function getLibraryArtistDetail(artist: string): Promise<LibraryArtistDetail> {
       // Current: returns tracks + albums
       // New: add:
       // - biography: string
       // - images: { banner, logo, photo }
       // - relatedArtists: [{ name, connectionType, connectionCount }]
       // - stats: { lastfmFollowers, recentScrobbles, libraryPlayCount }
   }
   ```

2. **Create Artist Shrine view:**
   ```tsx
   // desktop/renderer-app/src/features/library/ArtistShrine.tsx
   export function ArtistShrine({ artist }: { artist: string }) {
     return (
       <div className="shrine">
         <header style={{ backgroundImage: `url(${bannerUrl})` }}>
           <img className="logo" src={logoUrl} alt={artist} />
           <h1>{artist}</h1>
           <p className="bio">{bio}</p>
         </header>
         
         <section className="timeline">
           {/* Band member timeline, formation, key albums */}
         </section>
         
         <section className="constellation">
           {/* Related artists - visual network */}
         </section>
         
         <section className="tracks">
           {/* Library tracks by this artist */}
         </section>
       </div>
     );
   }
   ```

3. **Wire to backend:**
   ```python
   # lyra_api.py
   @app.route('/api/artist/shrine/<artist>', methods=['GET'])
   def api_artist_shrine(artist: str):
       """Get comprehensive artist profile for Shrine view."""
       return {
           'artist': artist,
           'biography': biographer.fetch_artist_bio(artist),
           'images': theaudiodb.fetch_images(artist),
           'related': lore.get_artist_connections(artist),
           'stats': lastfm.get_artist_stats(artist),
           'library_stats': db_stats,
       }
   ```

### 3.2 Visualize the Constellation (Network View) ⚠️ COMPONENT EXISTS, NO DATA

**Status:** 15% complete | **Priority:** P1 (flagship feature)

**What's built:**
- ✅ `ConstellationScene.tsx` component (renders D3/canvas graph layout)
- ✅ Route `/oracle` (loads Constellation)
- ✅ Mock data: `constellationNodes` and `constellationEdges` (hardcoded)

**What's missing:**
- ❌ **Live data from connections table**
  - Currently: Returns mock data (["Queen", "David Bowie", "Mick Jagger"], etc.)
  - Should: Query connections graph based on user's library

- ❌ **Filtering + interaction**
  - Should be able to filter by: genre, era, connection type (samples/collaborated/influenced)
  - Should be able to click node → drill down to artist shrine

- ❌ **Force-directed layout algorithm**
  - Current: Simple concentric ring layout
  - Should: Physics-based layout (nodes repel, edges attract) for organic feel

**Backend endpoint to add:**

```python
# lyra_api.py
@app.route('/api/constellation', methods=['GET'])
def api_constellation():
    """Get full connections graph for visualization."""
    params = request.args
    genre_filter = params.get('genre')
    era_filter = params.get('era')
    connection_type = params.get('type', 'all')
    
    conn = get_connection()
    c = conn.cursor()
    
    # Query connections table with filters
    # Build nodes: unique artists + their metadata
    # Build edges: connection relationships
    
    return jsonify({
        'nodes': [
            { 'id': str, 'label': str, 'genre': str, 'era': str, 'inLibrary': bool }
        ],
        'edges': [
            { 'source': str, 'target': str, 'type': str, 'weight': float }
        ]
    })

@app.route('/api/constellation/filters', methods=['GET'])
def api_constellation_filters():
    """Get available filter options for Constellation."""
    return jsonify({
        'genres': [...],
        'eras': [...],
        'connectionTypes': ['collaborated', 'influenced', 'sampled', 'member-of', 'toured-with']
    })
```

**Frontend improvements:**

```tsx
// desktop/renderer-app/src/features/constellation/ConstellationScene.tsx

export function ConstellationScene() {
  const [genre, setGenre] = useState<string | null>(null);
  const [era, setEra] = useState<string | null>(null);
  const { data: constellation } = useQuery({
    queryKey: ['constellation', genre, era],
    queryFn: () => getConstellation({ genre, era })
  });

  // Add force simulation for organic layout
  const layout = useForceDirectedLayout(nodes, edges);
  
  // Add click handlers for drill-down
  const handleNodeClick = (node) => {
    navigate(`/artist/${node.id}`);  // Go to ArtistShrine
  };

  return (
    <div className="constellation">
      <filters>
        <select onChange={(e) => setGenre(e.target.value)}>
          {/* Genre options */}
        </select>
        <select onChange={(e) => setEra(e.target.value)}>
          {/* Era options */}
        </select>
      </filters>
      
      <SVGCanvas nodes={layout} edges={edges} onNodeClick={handleNodeClick} />
    </div>
  );
}
```

### 3.3 Implement "Status Check" Benchmarking ❌ NOT BUILT

**Status:** 0% complete | **Priority:** P2 (nice-to-have)

**What it should show:**
A **"Taste Profile" report** that compares your collection against global baselines:

```
┌─────────────────────────────────────────────────────────┐
│  YOUR TASTE PROFILE vs. BASELINE                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🔊 ENERGY                                              │
│     Your avg: 0.62     Global avg: 0.55  [HIGHER ▲]   │
│                                                         │
│  😊 VALENCE                                             │
│     Your avg: 0.41     Global avg: 0.52  [LOWER ▼]    │
│     → You prefer melancholic, introspective music       │
│                                                         │
│  🎯 OBSCURITY                                           │
│     Your curated %: 23%HighAcclaim / 8% Mainstream    │
│     → You actively seek cult classics                  │
│                                                         │
│  ⏱️  DIVERSITY BY ERA                                   │
│     1970s: 8% | 1980s: 12% | 1990s: 24% | 2000s: 31% │
│     2010s: 18% | 2020s: 7%                             │
│     → Weighted toward 2000s-2010s alt/indie            │
│                                                         │
│  🌍 DISCOVERY VELOCITY                                  │
│     This month: 12 new artists | Last month: 8         │
│     Avg discovery rate: 6.4/month                       │
│     → 47% faster than baseline explorers               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Metrics to compute:**

| Metric | Source | Calculation |
|--------|--------|-------------|
| Energy avg | `track_scores.energy` | Mean across library |
| Valence avg | `track_scores.valence` | Mean across library |
| Obscurity % | `lastfm.scrobble_count` | % < 50th percentile |
| High acclaim % | `discogs.rating` + `genius.votes` | % > 75th percentile |
| Era distribution | `tracks.year` | Histogram bins |
| Main genres | `tracks.genre` | Top 5 by track count |
| Discovery velocity | `tracks.added_at` | Tracks added per month |
| Scene concentration | `connections.type` | % of library connected via scene |

**Backend endpoint to add:**

```python
# lyra_api.py
@app.route('/api/taste/profile', methods=['GET'])
def api_taste_profile():
    """
    Compute comprehensive taste profile vs. global baseline.
    Runs ~1-2s on 2000+ track library.
    """
    return jsonify({
        'energy': {
            'your_avg': 0.62,
            'baseline_avg': 0.55,
            'percentile': 0.68,  # You're in top 32%
            'description': 'Higher energy than average'
        },
        'valence': { ... },
        'obscurity': {
            'high_acclaim_pct': 23,
            'mainstream_pct': 8,
            'description': 'Strong preference for quality over popularity'
        },
        'era_distribution': [
            { 'era': '1970s', 'pct': 8 },
            { 'era': '1980s', 'pct': 12 },
            ...
        ],
        'genres': [
            { 'genre': 'Alternative Rock', 'count': 234, 'pct': 18 },
            ...
        ],
        'discovery_velocity': {
            'this_month': 12,
            'last_month': 8,
            'avg_monthly': 6.4,
            'trend': 'accelerating'
        },
        'scene_diversity': {
            'main_scenes': ['Britpop', 'Shoegaze', 'Post-Rock'],
            'scene_connectivity': 0.45,  # 0-1: how connected your scenes are
        }
    })
```

**Frontend component:**

```tsx
// desktop/renderer-app/src/features/oracle/TasteProfileCard.tsx
export function TasteProfileCard() {
  const { data: profile } = useQuery({
    queryKey: ['taste-profile'],
    queryFn: () => getTasteProfile()
  });

  return (
    <div className="taste-profile">
      <h2>Your Taste Profile</h2>
      
      <MetricCard
        label="Energy"
        yourValue={profile.energy.your_avg}
        baselineValue={profile.energy.baseline_avg}
        description={profile.energy.description}
      />
      
      <MetricCard label="Valence" {...profile.valence} />
      
      <MetricCard
        label="Obscurity Index"
        value={profile.obscurity.high_acclaim_pct}
        description={profile.obscurity.description}
      />
      
      {/* Era timeline chart */}
      <AreaChart data={profile.era_distribution} />
      
      {/* Genre pie chart */}
      <PieChart data={profile.genres} />
      
      {/* Discovery velocity trend */}
      <LineChart data={profile.discovery_velocity} />
    </div>
  );
}
```

---

---

# PHASE 3B: EXPAND EXISTING FEATURES

These are half-built features that should be completed alongside the 3-phase rollout.

### 3B.1 Emotional Arc System (Playlist sequencing) ⚠️ PARTIALLY BUILT

**Status:** 60% complete | **Priority:** P1 (core UX)

**What's built:**
- ✅ `arc.py` - Emotional arc mapper
- ✅ `EmotionalArcStrip.tsx` - Visual arc visualization
- ✅ Arc types: linear, climax, valley, plateau

**What's missing:**
- ❌ **Interactive arc editing** - drag track to change arc position
- ❌ **Arc templates** library - "Epic Journey", "Comedown", "Deep Dive", etc.
- ❌ **Auto-resequence button** - regenerate arc while keeping track list

**Quick wins:**
- Add drag-to-reorder in TrackTable
- Pre-compute 5 arc templates + store in DB
- Add "Auto-resequence" button to PlaylistHero

### 3B.2 Dimensional Search UI ⚠️ EXISTS, NEEDS EXPANSION

**Status:** 50% complete | **Priority:** P1 (core search)

**What's built:**
- ✅ Dimensional scoring (10 dimensions in `anchors.py`)
- ✅ Text-to-dimension parsing
- ✅ CLAP semantic search

**What's missing:**
- ❌ **Visual sliders for dimensional search** in UI
- ❌ **Preset filters** ("Chill Evening", "Late Night Coding", "Gym Session")
- ❌ **Saved search history** (allow users to re-run searches)

**Build:**
```tsx
// desktop/renderer-app/src/features/search/DimensionalSearchPanel.tsx
export function DimensionalSearchPanel() {
  const [energy, setEnergy] = useState(0.5);
  const [valence, setValence] = useState(0.5);
  const [warmth, setWarmth] = useState(0.5);
  // ... etc
  
  const { data: results } = useQuery({
    queryKey: ['dimensional-search', { energy, valence, warmth }],
    queryFn: () => searchDimensional({ energy, valence, warmth })
  });

  return (
    <div className="dimensional-search">
      <Slider label="Energy" value={energy} onChange={setEnergy} />
      <Slider label="Valence" value={valence} onChange={setValence} />
      {/* ... */}
      <TrackList tracks={results} />
    </div>
  );
}
```

---

---

# ROADMAP: WHAT TO BUILD NEXT (Priority Order)

## Sprint 1 (Biographer + API Setup) — 2 weeks
- [ ] **Add Biographer module** (`oracle/enrichers/biographer.py`)
  - Integrate TheAudioDB for imagery
  - Fetch artist biographies from Wikipedia/Last.fm
  - Store in `enrich_cache` table
- [ ] **Add `POST /api/enrich/biographer` endpoint**
- [ ] **Add TheAudioDB key to `.env.template`**
- [ ] **Run enricher on all artists in library** (batch job)

## Sprint 2 (Constellation Live Data) — 2 weeks
- [ ] **Query `connections` table**
  - Build nodes + edges list from artist relationships
  - Add genre/era metadata to each node
- [ ] **Implement `GET /api/constellation` endpoint**
- [ ] **Update ConstellationScene to use live data** (not mock)
- [ ] **Add filtering UI** (genre, era, connection type)

## Sprint 3 (Artist Shrine) — 1.5 weeks
- [ ] **Extend `getLibraryArtistDetail()` to include biography + images**
- [ ] **Create ArtistShrine view** component
- [ ] **Add related-artists section** (visual cards)
- [ ] **Wire up routes** to navigate from Constellation → Shrine

## Sprint 4 (Taste Profile Benchmarking) — 1.5 weeks
- [ ] **Implement taste profile computation** (`GET /api/taste/profile`)
- [ ] **Create TasteProfileCard component**
- [ ] **Add charts** (era distribution, genre breakdown, discovery velocity)

## Sprint 5 (Deep Cut Discovery) — 1.5 weeks
- [ ] **Implement DeepCut module** (high acclaim, low popularity filtering)
- [ ] **Extend Scout** to support taste-aware discovery
- [ ] **Add UI** to trigger Scout hunts with filters

## Sprint 6 (Pathfinder) — 1.5 weeks
- [ ] **Implement `/api/pathfinder/trace` endpoint**
- [ ] **Implement `/api/pathfinder/explore` endpoint**
- [ ] **Create Pathfinder UI** (interactive graph visualization)

---

---

# APPENDIX: FEATURES ALREADY BUILT (Don't Duplicate!)

### Data Layer ✅
- `tracks` table (filepath, artist, title, metadata)
- `track_scores` (10 dimensions: energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia)
- `connections` (artist relationships)
- `track_structure` (BPM, key, drops, energy profile)
- `playback_history` (skip signals, ratings)
- `taste_profile` (dimensional preferences)
- `sample_lineage` (sample origins)

### Discovery Engines ✅
- `scout.py` - Bridge artist hunting (Discogs + local library)
- `lore.py` - Artist lineage & collaborations (MusicBrainz relationships)
- `dna.py` - Sample tracing (local DB + WhoSampled stubs)
- `architect.py` - Audio structure (BPM, key, drops via librosa)
- `radio.py` - Smart radio (Chaos/Flow/Discovery modes)

### Enrichment ✅
- `musicbrainz.py` - Metadata + relationships
- `acoustid.py` - Audio fingerprinting
- `discogs.py` - Release info, labels, genres
- `lastfm.py` - Artist stats, tags, playback context
- `genius.py` - Lyrics, song facts
- `essentia.py` - Audio analysis (mood, BPM, etc.)

### Search ✅
- CLAP embeddings (512-dim, cosine similarity)
- ChromaDB vector store
- Text + audio semantic search

### UI Components ✅
- ConstellationScene (graph visualization)
- EmotionalArcStrip (timeline visualization)
- TrackTable, SearchResultStack
- PlaylistHero, PlaylistNarrative
- DossierDrawer (track details)
- BottomTransportDock (player controls)

### Endpoints ✅
- `/api/search` (semantic + dimensional)
- `/api/library/*` (tracks, artists, albums)
- `/api/vibes/*` (save, materialize, refresh)
- `/api/scout/cross-genre` (bridge artist hunting)
- `/api/lore/trace` + `/api/lore/connections` (artist lineage)
- `/api/dna/trace` + `/api/dna/pivot` (sample tracing)
- `/api/architect/analyze` (audio structure)
- `/api/radio/*` (Chaos/Flow/Discovery)

---

---

# FINAL NOTES

**The Oracle of Culture is waiting to be woken up.** You have:
1. ✅ The data foundation (2,472 tracks, embeddings, relationships)
2. ✅ The engines (Scout, Lore, DNA, Architect, Radio)
3. ✅ 60% of the UI

What remains is wiring it all together and adding the last 40%—primarily:
- Biographer module (culture context)
- Constellation live data (relationship visualization)
- Artist Shrines (cultural storytelling)
- Taste Profile reporting (self-knowledge)
- Deep Cut discovery (finding hidden gems)

Each adds a layer of **meaning** and **serendipity** on top of the raw music mechanics. That's what makes Lyra an **Oracle**—not just a recommender, but a **teacher** of culture and taste.

