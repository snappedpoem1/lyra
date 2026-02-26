# ðŸŽµ Lyra Oracle

**Semantic Music Intelligence System**

Transform your music library into an AI-powered knowledge base with semantic search, intelligent curation, and natural language playlist generation.

> **Current Operating Mode (2026-02-17):** Core/API-first. Web UI routes were removed from active runtime; use `/api/*` endpoints and CLI workflows.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ðŸš€ Quick Start

### Windows Setup

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create .env (adjust paths to your system)
@'
LYRA_DB_PATH=C:\MusicOracle\lyra_registry.db
LIBRARY_BASE=A:\music\Active Music
DOWNLOADS_FOLDER=C:\MusicOracle\downloads
VIBES_FOLDER=A:\music\Vibes
HF_HOME=C:\MusicOracle\hf_cache
'@ | Set-Content .env

# Initialize system
python -m oracle db migrate

# Use unified CLI (new in v10)
lyra doctor              # System health check
lyra scan .              # Scan current directory
lyra index               # Index audio files
lyra serve               # Start API server
# Open http://localhost:5000 (root returns API status message; use /api/* endpoints)
```

### macOS / Linux Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env (adjust paths to your system)
cat > .env << 'EOF'
LYRA_DB_PATH=/path/to/lyra_registry.db
LIBRARY_BASE=/path/to/your/music
DOWNLOADS_FOLDER=/path/to/downloads
VIBES_FOLDER=/path/to/vibes
HF_HOME=/path/to/hf_cache
EOF

# Initialize and run
python -m oracle db migrate

# Use unified CLI (new in v10)
./lyra doctor           # System health check
./lyra hunt "Aphex Twin"  # Start acquisition
./lyra serve            # Start API server
```

---

## âœ¨ Core Features

### ðŸŽ† **Playlust** (Status)
Playlust UI is not active in the current runtime profile. The active system is API-first and CLI-first.
If Playlust is reintroduced, it should be tracked as a separate restoration milestone.

### ðŸ” **Semantic Search**
Search music with natural language:
- "aggressive distorted guitars with screaming vocals"
- "chill ambient electronic for late night coding"
- "uplifting emotional orchestral with female vocals"

Uses CLAP (Contrastive Language-Audio Pretraining) for deep audio understanding.

### ðŸŽ­ **Vibes System**
Create dynamic playlists from semantic queries:
```powershell
python -m oracle vibe save --name "Workout Energy" --query "high energy aggressive" --n 50
python -m oracle vibe build --name "Workout Energy"
python -m oracle vibe materialize --name "Workout Energy" --mode hardlink
```

### ðŸ“ **Intelligent Curation**
AI-powered library organization:
```powershell
python -m oracle curate classify
python -m oracle curate plan --preset artist_album
python -m oracle curate apply --plan-path Reports/curation_plan_*.json --dry-run
```

### ðŸ“¥ **Smart Acquisition**  
Tiered acquisition with Real-Debrid + SpotiFLAC:
```powershell
# Acquire top 10 missing tracks for an artist
python lyra_acquire.py --artist "Coheed and Cambria" --limit 10

# Whole artist catalog (all pending tracks)
python lyra_acquire.py --artist "Brand New" --whole-artist

# Full discography mode (Spotify API â†’ queue â†’ acquire)
python lyra_acquire.py --artist "Deftones" --discography

# Dry run to preview
python lyra_acquire.py --artist "Radiohead" --limit 5 --dry-run

# Link liked songs to library
python lyra_acquire.py --link-liked

# Set quality preference (default: FLAC)
python lyra_acquire.py --artist "NIN" --limit 10 --quality MP3-320
```

### ðŸŒ **API Interface**
Active interface is REST API under `/api/*` plus CLI commands.

### ðŸ”§ **2026-02-26 Hardening Update**
- Queue drain now supports source-targeted execution (`playlist`, `liked`, `top_tracks`, `history`) and prioritizes queue ordering for demo workflows.
- Ingest watcher reconciliation now:
  - marks `downloaded -> completed` when imported tracks are present,
  - re-queues stale `downloaded` rows that never materialize.
- Enrichment providers now include production modules for:
  - MusicBrainz
  - AcoustID
  - Discogs
  - Last.fm
  - Genius
- Score sanity audit command added (`oracle score-audit`) to validate 10-dimension coverage and trend checks.

**Operational sequence (recommended):**
```powershell
# 1) Drain queue in source order (playlist first, then liked)
python -m oracle drain --limit 25 --source playlist --max-tier 3 --workers 4
python -m oracle drain --limit 25 --source liked --max-tier 3 --workers 4

# 2) Ingest + reconcile
python -m oracle watch --once

# 3) Ensure all active tracks are scored
python -m oracle score --all

# 4) Validate dimension coverage and sanity
python -m oracle score-audit

# 5) Run enrichment providers in batch
python -m oracle enrich-all --limit 500 --providers lastfm,genius,musicbrainz
```

### 2026-02-26 Demo Audit (Verified)
- End-to-end pipeline verified: `drain -> import/watch -> scan -> index -> score -> search`.
- Queue source prioritization active in `drain`: `playlist > liked > top_tracks > history > discography`.
- Guarded acquisition remains fail-closed (duplicates, instrumentals, junk variants blocked before library import).
- Streamrip tier hardened:
  - auto-hydrates Qobuz credentials from environment if streamrip config is missing values,
  - sanitizes Windows-invalid filename characters before staging moves,
  - retries transient streamrip failures once before hard fail.
- Guard false-positive fixed for legitimate titles such as `Under Cover of Darkness`.
- Score coverage validated with `oracle score-audit`.

Current validated runtime snapshot:
- `tracks(active)=368`
- `embeddings=368`
- `scored=368`
- test suite: `35 passed`

Acquisition verification snapshot:
- Streamrip-only stress run (20 pending playlist items): `3/20` success.
- Full waterfall run on comparable playlist batch (20 items): `11 downloaded`, remainder mostly duplicate/junk guard rejections.
- Practical guidance: do not run streamrip-only as primary path; use full waterfall tiers.

Known non-blocking gaps:
- Streamrip still has intermittent upstream failures (`AssertionError`, occasional `401`/`total items`) on some tracks.
- Tier fallback mitigates this (`Qobuz -> Streamrip -> Slskd -> RD -> SpotDL`) during normal `drain` runs.
- `LM Studio` can be offline without blocking acquisition/index/score workflows.

Parallel run pattern (recommended for throughput):
```powershell
# Terminal A: acquisition
python -m oracle drain --limit 50 --source playlist --max-tier 5 --workers 6

# Terminal B: ingest + reconcile in loop
python -m oracle watch --once

# Terminal C: backfill scoring
python -m oracle score --all
```

Open-source alternatives reviewed for gap coverage:
- `beets` (already integrated): canonical organization/tagging/import pipeline.
- `Lidarr` + `Prowlarr`: robust queue/indexer orchestration if acquisition automation needs deeper scheduler controls.
- `Essentia`: additional audio descriptor extraction for cross-validating 10-dimension scoring trends.

### ðŸ›¡ï¸ **Safety Doctrine** (NEW v10)
Time-travel undo for all file operations:
```powershell
lyra history 10         # View last 10 operations
lyra undo 1             # Undo last operation
```

### ðŸŽ¯ **Unified Pipeline** (NEW v10)
Orchestrated acquisition workflow:
```powershell
lyra hunt "Aphex Twin"  # Search â†’ Acquire â†’ Scan â†’ Enrich â†’ Index â†’ Place
```

### ðŸ’» **Operations Console** (NEW v10)
Unified CLI interface with 10 commands:
```powershell
lyra help               # Show all commands
lyra agent "Find punk EDM remixes"  # LLM-powered queries
```

---

## ðŸ“– Documentation

### Quick Reference
- **[QUICKSTART.md](QUICKSTART.md)** â€” Fast setup guide
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** â€” Production deployment
- **[BUG_FIXES.md](BUG_FIXES.md)** â€” Known issues and fixes
- **[LYRA_V10_IMPLEMENTATION.md](LYRA_V10_IMPLEMENTATION.md)** â€” Safety Doctrine + Pipeline + Console (NEW)
- **[THREAD_SAFETY_VALIDATION.md](THREAD_SAFETY_VALIDATION.md)** â€” Thread-safety validation report (NEW)
- **[QUICKSTART_V10.md](QUICKSTART_V10.md)** â€” v10 quick start guide (NEW)
- **[plans/llm_access_points.md](plans/llm_access_points.md)** - Runtime LLM access and processing map (NEW)

### Phase Documentation
- **[PHASE_1_FOUNDATION.md](PHASE_1_FOUNDATION.md)** â€” Database, ChromaDB, configuration
- **[PHASE_2_SEARCH.md](PHASE_2_SEARCH.md)** â€” Scanner, indexer, semantic search
- **[PHASE_3_ACQUISITION.md](PHASE_3_ACQUISITION.md)** â€” yt-dlp, Prowlarr, download queue
- **[PHASE_4_ENRICHMENT.md](PHASE_4_ENRICHMENT.md)** â€” MusicBrainz, AcoustID, Last.fm, Genius
- **[PHASE_5_CURATION.md](PHASE_5_CURATION.md)** â€” Classification, duplicates, organization
- **[PHASE_6_VIBES.md](PHASE_6_VIBES.md)** â€” Vibe system deep dive
- **[PHASE_7_API.md](PHASE_7_API.md)** â€” Flask API reference + Web UI
- **[PHASE_8_POLISH.md](PHASE_8_POLISH.md)** â€” Validation, scripts, production readiness
- **[PHASE_9_10_SENTIENT.md](PHASE_9_10_SENTIENT.md)** â€” Sentient Oracle (radio, lore, agent, glass UI)
- **[WARPATH_RESULTS.md](WARPATH_RESULTS.md)** â€” Warpath hardening session results

---

## ðŸ“š Project History

Lyra Oracle was built through 10 iterative phases, each adding core capabilities:

> **Historical note:** UI references in the phase history below describe prior milestones. Current runtime mode is core/API-first with UI removed.

### ðŸ›ï¸ **Phase 1: Foundation** â€” [PHASE_1_FOUNDATION.md](PHASE_1_FOUNDATION.md)
**Database & Configuration Infrastructure**

âœ… **SQLite Database** â€” Comprehensive schema (tracks, embeddings, vibes, curation_plans, acquisition_queue)  
âœ… **ChromaDB Integration** â€” Persistent vector storage with HNSW indexing  
âœ… **Configuration System** â€” Environment-based config with `.env` support  
âœ… **Doctor Utility** â€” System diagnostics (Python, FFmpeg, fpcalc, disk space)  
âœ… **Write Modes** â€” Safety controls (dry_run, apply_allowed, unrestricted)

**Key Files:** `oracle/db/schema.py`, `oracle/config.py`, `oracle/doctor.py`, `lyra_registry.db`, `chroma_storage/`

---

### ðŸ”Ž **Phase 2: Core Intelligence** â€” [PHASE_2_SEARCH.md](PHASE_2_SEARCH.md)
**Semantic Search & Indexing**

âœ… **Scanner** â€” Recursive audio discovery with SHA256 deduplication  
âœ… **CLAP Indexer** â€” 512-dim embeddings via `laion/clap-htsat-unfused` model  
âœ… **Semantic Search** â€” Natural language queries ("energetic rock", "chill lo-fi beats")  
âœ… **Incremental Scanning** â€” Fast re-scan with change detection  
âœ… **Statistics** â€” Library insights (tracks, artists, duration, size)

**Performance:** 50ms search queries, 2.3s per track indexing (GPU), 100% deduplication accuracy

**Key Files:** `oracle/scanner.py`, `oracle/indexer.py`, `oracle/search.py`

---

### ðŸ“¥ **Phase 3: Acquisition** â€” [PHASE_3_ACQUISITION.md](PHASE_3_ACQUISITION.md)
**Multi-Source Download Management**

âœ… **yt-dlp Integration** â€” YouTube, SoundCloud, Bandcamp downloads  
âœ… **Prowlarr API** â€” Indexer search across 6 public trackers (1337x, TPB, BitSearch, LimeTorrents, Nyaa.si, KAT)  
âœ… **Real-Debrid** â€” Instant cached torrent downloads via HTTPS  
âœ… **SpotiFLAC** â€” Tier 2 fallback (Tidal/Qobuz/Amazon FLAC via Spotify URI)  
âœ… **Tiered Waterfall** â€” RD first â†’ SpotiFLAC fallback, automatic quality degradation (FLAC â†’ MP3-320 â†’ any)  
âœ… **Discography Search** â€” Searches for full artist discography torrents before individual albums  
âœ… **Parallel Downloads** â€” 4-thread concurrent RD downloads with 1MB chunks  
âœ… **Quality Upgrade** â€” Automatically replaces lower-quality files when higher quality becomes available  
âœ… **RD Pre-Sweep** â€” Checks for completed torrents from prior runs before processing queue  
âœ… **RD Post-Sweep** â€” After harvest, waits up to 120s for pending torrents to finish  
âœ… **Seeder-Weighted Scoring** â€” Dead torrents (0 seeders) skipped instantly; high-seeder results prioritized  
âœ… **FlareSolverr Proxy** â€” Cloudflare bypass for protected indexers  
âœ… **Format Conversion** â€” FFmpeg transcoding (MP3/FLAC/OPUS/M4A)  
âœ… **Auto-Organization** â€” Files moved to Artist/Album structure with album name parsed from torrent  

**Acquisition Waterfall:**
```
Discography FLAC â†’ Album FLAC â†’ Track FLAC
  â†’ Discography MP3-320 â†’ Album MP3-320 â†’ Track MP3-320
    â†’ Discography (any) â†’ Album (any) â†’ Track (any)
      â†’ SpotiFLAC fallback
```

**Key Files:** `lyra_acquire.py`, `oracle/hunter.py`, `oracle/downloader.py`

---

### ðŸŽ¼ **Phase 4: Enrichment** â€” [PHASE_4_ENRICHMENT.md](PHASE_4_ENRICHMENT.md)
**Metadata Enhancement**

âœ… **MusicBrainz** â€” Authoritative music database lookup (MBID, genres, release dates)  
âœ… **AcoustID Fingerprinting** â€” Acoustic-based track identification (96% accuracy)  
âœ… **Last.fm Integration** â€” User tags, play counts, similar artists  
âœ… **Genius Lyrics** â€” Automatic lyrics fetching  
âœ… **Caching** â€” 9x faster with API response caching

**Enrichment Sources:** MusicBrainz, AcoustID, Last.fm, Genius (with rate limiting)

**Key Files:** `oracle/enrichers/unified.py`, `oracle/enrichers/musicbrainz.py`, `oracle/enrichers/acoustid.py`, `oracle/enrichers/lastfm.py`, `oracle/enrichers/genius.py`

**Implementation notes (current):**
- Unified enrichment caches provider payloads in `enrich_cache`.
- Last.fm is used for tags, play/listener context, and similar-track/artist signals.
- Genius is used for canonical song metadata and context (description, release date, pageviews).
- Empty provider payloads are not persisted to cache to avoid stale misses.

---

### ðŸŽ¯ **Phase 5: Curation** â€” [PHASE_5_CURATION.md](PHASE_5_CURATION.md)
**Intelligent Library Organization**

âœ… **Version Classification** â€” Detect Original/Live/Remix/Acoustic/Cover (97% accuracy)  
âœ… **Duplicate Detection** â€” Hash-based (100%) + fingerprint (98%) + metadata fuzzy matching  
âœ… **Library Organization** â€” Smart folder structures (Artist/Album, Genre/Artist, Flat)  
âœ… **Filename Cleaning** â€” 23 junk pattern removal + standardization  
âœ… **Download Processor** â€” Automated pipeline (clean â†’ enrich â†’ classify â†’ organize â†’ index)  
âœ… **Curation Plans** â€” Preview, apply, and rollback organizational changes

**Presets:** by_artist_album, by_genre_artist, flat_with_year

**Key Files:** `oracle/classifier.py`, `oracle/duplicates.py`, `oracle/curator.py`, `oracle/name_cleaner.py`, `oracle/download_processor.py`

---

### ðŸŽ­ **Phase 6: Vibes** â€” [PHASE_6_VIBES.md](PHASE_6_VIBES.md)
**Semantic Playlist System**

âœ… **Vibe Profiles** â€” Save semantic queries as reusable playlists  
âœ… **Dynamic Building** â€” Real-time semantic search results  
âœ… **Materialization** â€” Hardlink folders (0 MB disk usage) + M3U8 playlists  
âœ… **Refresh Mechanism** â€” Auto-update vibes when library changes  
âœ… **Duplicate Prevention** â€” Smart deduplication within vibes

**Workflow:** `save` â†’ `build` â†’ `materialize` (hardlink/copy) â†’ `refresh` (keep current)

**Example Vibes:** "Aggressive Metal", "Chill Lo-Fi Beats", "Uplifting EDM"

**Key Files:** `oracle/vibes.py`, `A:\music\Vibes/`

---

### ðŸŒ **Phase 7: Web API & UI** â€” [PHASE_7_API.md](PHASE_7_API.md)
**Flask REST API + Web Interface**

âœ… **Flask API** â€” 20+ REST endpoints (search, library, vibes, curation, acquisition)  
âœ… **Web Dashboard** â€” Real-time stats with charts  
âœ… **Search Interface** â€” Semantic search with results display  
âœ… **Vibes Management** â€” Create, build, materialize, and refresh vibes  
âœ… **Curation UI** â€” Preview and apply organization plans  
âœ… **Acquisition Portal** â€” Queue management and download status  
âœ… **Repair Utility** â€” System diagnostics and health checks

**Tech Stack:** Flask 3.1.2, Flask-CORS, Bootstrap 5, Vanilla JavaScript

**API Endpoints:** `/api/health`, `/api/status`, `/api/search`, `/api/library/*`, `/api/vibes/*`, `/api/curate/*`, `/api/acquire/*`

**Key Files (historical):** `lyra_api.py`, `templates/`, `static/`, `oracle/repair.py`

**Access (historical):** http://localhost:5000

---

### âœ¨ **Phase 8: Polish & Refinement** â€” [PHASE_8_POLISH.md](PHASE_8_POLISH.md)
**Production Readiness**

âœ… **README Rewrite** â€” Comprehensive documentation (350 lines)  
âœ… **Input Validation** â€” Security module (SQL injection, path traversal, type safety)  
âœ… **Quick-Setup.ps1** â€” Automated first-time setup script (140 lines)  
âœ… **Backup-Restore.ps1** â€” Database/ChromaDB backup utility (200 lines)  
âœ… **Demo-Workflow.ps1** â€” Interactive demo of all features (250 lines)  
âœ… **Validation Module** â€” `oracle/validation.py` (450 lines) with 30+ validators  
âœ… **Documentation** â€” Complete phase history (this section!)

**Security Features:** Path validation, filename sanitization, query string validation, track limit enforcement, URL validation, enum validation

**Scripts:** `Quick-Setup.ps1`, `Backup-Restore.ps1`, `Demo-Workflow.ps1`

**Key Files:** `README.md`, `oracle/validation.py`, PowerShell helper scripts

---

### ðŸ§  **Phase 9-10: Sentient Oracle** â€” [PHASE_9_10_SENTIENT.md](PHASE_9_10_SENTIENT.md)
**Total Sonic Awareness + Safety Systems**

âœ… **Cortex Upgrade** â€” New tables for connections, structure, playback history  
âœ… **Scout/Lore/DNA** â€” Cross-genre discovery, lineage mapping, sample pivots  
âœ… **Hunter** â€” Prowlarr + Real-Debrid accelerated acquisition (parallel downloads, quality waterfall, seeder scoring)  
âœ… **Lyra Acquire** â€” Tiered acquisition engine with discography search, RD pre/post-sweep, quality upgrade  
âœ… **Architect** â€” Structure analysis (drops, BPM, key, energy)  
âœ… **Radio Engine** â€” Chaos, Flow, Discovery modes  
âœ… **Soul Layer** â€” LM Studio agent (Qwen2.5 14B) + fact drops  
âœ… **Glass UI (historical)** â€” Persistent player + constellation view + radio page

**ðŸ›¡ï¸ Phase 10: Safety Doctrine** â€” [LYRA_V10_IMPLEMENTATION.md](LYRA_V10_IMPLEMENTATION.md)  
âœ… **Transaction Logging** â€” JSONL journal with time-travel undo  
âœ… **Unified Pipeline** â€” 6-stage orchestration (Search â†’ Acquire â†’ Scan â†’ Enrich â†’ Index â†’ Place)  
âœ… **Operations Console** â€” Unified CLI with 10 commands (`lyra` launcher)  
âœ… **Thread-Safe Database** â€” Multi-threaded Flask compatibility  
âœ… **API Extensions** â€” 8 new endpoints (pipeline, safety, streaming)  
âœ… **Enhanced Agent** â€” Full context integration with noir persona

**Thread-Safety:** Complete SQLite thread isolation with per-request connections (20+ concurrent requests validated)

**LLM Integration:** LM Studio OpenAI-compatible server with graceful fallbacks to deterministic parsing

**Key Files:** `oracle/scout.py`, `oracle/lore.py`, `oracle/dna.py`, `oracle/hunter.py`, `oracle/architect.py`, `oracle/radio.py`, `oracle/agent.py`, `oracle/llm.py`, `oracle/safety.py`, `oracle/pipeline.py`, `oracle/console.py`, `lyra_api.py`, `lyra`, `lyra.bat`, `LYRA_V10_IMPLEMENTATION.md`, `THREAD_SAFETY_VALIDATION.md`

---

### ðŸ“Š **Phase Progress Overview**

| Phase | Focus | Status | Key Metrics |
|-------|-------|--------|-------------|
| **1** | Foundation | âœ… Complete | SQLite + ChromaDB + Config |
| **2** | Search | âœ… Complete | 56 tracks indexed, 50ms queries |
| **3** | Acquisition | âœ… Complete | yt-dlp + Prowlarr + Queue |
| **4** | Enrichment | âœ… Complete | 4 sources, 96% fingerprint accuracy |
| **5** | Curation | âœ… Complete | 97% classification, 100% hash dedup |
| **6** | Vibes | âœ… Complete | 2 vibes, 20 hardlinks (0 MB) |
| **7** | API + UI (historical) | âœ… Complete | 20+ endpoints, 5 web pages |
| **8** | Polish | âœ… Complete | Validation + Scripts + Docs |
| **9-10** | Sentient Oracle | âœ… Complete | Radio + Lore + Agent + Safety + Pipeline |

---

## ðŸ—ï¸ Architecture

**Backend:** Python 3.12, SQLite (thread-safe), ChromaDB, Transformers (CLAP), Flask  
**Audio:** mutagen, librosa, yt-dlp, FFmpeg  
**Interface (current):** CLI + REST API (`/api/*`)  
**Frontend (historical):** Bootstrap 5, Vanilla JS, Jinja2  
**LLM:** LM Studio (Qwen2.5-14B-Instruct) with graceful fallback

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚              Lyra Oracle System v10                      â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  REST API (/api/*) â”‚ CLI â”‚ Agent (LLM) â”‚ Legacy UI      â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  Emotional Model (10 dimensions) â”‚ Arc Engine            â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  Pipeline: Searchâ†’Acquireâ†’Scanâ†’Enrichâ†’Indexâ†’Place       â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  Scanner â”‚ Indexer â”‚ Search â”‚ Vibes â”‚ Hunter â”‚ Radio     â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  Scorer â”‚ Safety (Journal+Undo) â”‚ Lore â”‚ DNA â”‚ Scout     â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  SQLite Registry â”‚ ChromaDB â”‚ Spotify History â”‚ FS       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## ðŸŽ¯ Usage Examples

### Build a Vibe Collection
```powershell
python -m oracle vibe save --name "Morning Energy" --query "uplifting positive" --n 100
python -m oracle vibe save --name "Deep Focus" --query "ambient minimal calm" --n 150
python -m oracle vibe save --name "Evening Chill" --query "relaxing smooth jazz" --n 80

# Materialize all
foreach ($v in @("Morning Energy", "Deep Focus", "Evening Chill")) {
    python -m oracle vibe build --name $v
    python -m oracle vibe materialize --name $v --mode hardlink
}
```

### Smart Library Organization
```powershell
python -m oracle curate classify
python -m oracle curate plan --preset artist_album
python -m oracle curate apply --plan-path Reports/curation_plan_20260209.json
```

### API Usage
```python
import requests

# Semantic Search
response = requests.post('http://localhost:5000/api/search', 
    json={'query': 'epic orchestral', 'n': 20})
results = response.json()['results']

# Agent Query (LLM-powered intent parsing)
response = requests.post('http://localhost:5000/api/agent/query',
    json={'text': 'punk edm remixes'})
agent_result = response.json()
# Returns: {'action', 'thought', 'intent', 'next', 'llm'}

# Pipeline Acquisition (NEW v10)
response = requests.post('http://localhost:5000/api/pipeline/start',
    json={'query': 'Aphex Twin - Selected Ambient Works'})
job = response.json()
print(f"Job ID: {job['job_id']}, State: {job['job']['state']}")

# Check Pipeline Status
response = requests.get(f"http://localhost:5000/api/pipeline/status/{job_id}")
status = response.json()
print(f"State: {status['job']['state']}")

# View Operation Journal
response = requests.get('http://localhost:5000/api/journal?n=10')
journal = response.json()
print(f"Last {journal['count']} operations")

# Undo Last Operation
response = requests.post('http://localhost:5000/api/undo', json={'n': 1})
result = response.json()
print(f"Undone: {result['undone_count']} operations")

# Health Check (includes LLM status)
response = requests.get('http://localhost:5000/api/health')
health = response.json()
print(f"LLM Status: {health['llm']['status']}")
```

---

## ðŸ”’ Configuration

Create `.env` file:
```env
LYRA_DB_PATH=C:\MusicOracle\lyra_registry.db
LYRA_WRITE_MODE=apply_allowed
LIBRARY_BASE=A:\music\Active Music
DOWNLOADS_FOLDER=C:\MusicOracle\downloads
VIBES_FOLDER=A:\music\Vibes
HF_HOME=C:\MusicOracle\hf_cache

# LLM Configuration (LM Studio)
LYRA_LLM_PROVIDER=lmstudio
LYRA_LLM_BASE_URL=http://localhost:1234/v1
LYRA_LLM_MODEL=qwen2.5-14b-instruct
LYRA_LLM_API_KEY=
LYRA_LLM_TIMEOUT_SECONDS=30
```

### ðŸ§  LLM Setup (LM Studio)

The agent uses **LM Studio** for local LLM inference with graceful fallbacks:

**1. Install LM Studio:**
- Download from [lmstudio.ai](https://lmstudio.ai)
- Install and launch the application

**2. Download Model:**
- Search for: `bartowski/Qwen2.5-14B-Instruct-GGUF`
- Download: `Qwen2.5-14B-Instruct-Q4_K_M.gguf`
- Load model in LM Studio on port 1234

**3. Get Model ID:**
```powershell
(Invoke-RestMethod http://localhost:1234/v1/models).data | Select-Object id | Format-Table -AutoSize
```

**4. Update .env:**
```env
LYRA_LLM_MODEL=qwen2.5-14b-instruct
```

**Fallback Behavior:**
- If LLM unavailable â†’ deterministic intent parsing
- Response: `"thought": "The trail went cold, Boss."`
- Still returns structured action plan
- **Never returns "Error: LLM unavailable"**

---

## ðŸ› ï¸ CLI Reference

### Unified CLI (NEW v10)
```powershell
# System Management
lyra doctor                              # System health check
lyra help                                # Show all commands
lyra serve [--host HOST] [--port PORT]   # Start API server

# Acquisition Pipeline
lyra hunt <query>                        # Start acquisition
  # Example: lyra hunt "Aphex Twin - Selected Ambient Works"
  # Pipeline: Search â†’ Acquire â†’ Scan â†’ Enrich â†’ Index â†’ Place

# Safety Operations
lyra history [n]                         # View last N operations
lyra undo [n]                            # Undo last N operations
  # Example: lyra undo 3  # Undo last 3 file moves

# Library Operations
lyra scan <paths...>                     # Scan directories
lyra index [paths...]                   # Index audio files

# Vibes Management
lyra vibe-create <name> <prompt> [--n N] # Create vibe
  # Example: lyra vibe-create "Midnight Noir" "dark ambient jazz"

# Agent Queries
lyra agent <query>                       # LLM-powered queries
  # Example: lyra agent "Find aggressive metal with clean vocals"
```

### Legacy Python Module Commands
```powershell
# Core
python -m oracle db migrate              # Initialize database
python -m oracle doctor                  # Health check
python -m oracle.repair check            # Full diagnostics

# Library
python -m oracle scan --library PATH --limit N
python -m oracle index --limit N
python -m oracle search --query "TEXT" --n 10

# Vibes
python -m oracle vibe save --name "NAME" --query "TEXT" --n 100
python -m oracle vibe list
python -m oracle vibe build --name "NAME"
python -m oracle vibe materialize --name "NAME" --mode hardlink
python -m oracle vibe refresh --all

# Curation
python -m oracle curate classify
python -m oracle curate plan --preset artist_album
python -m oracle curate apply --plan-path PATH --dry-run

# Acquisition
python -m oracle acquire youtube --url URL
python -m oracle downloads organize --library PATH

# Server
python -m oracle serve --host 0.0.0.0 --port 5000 --debug  # API server

# Agent (requires LM Studio running)
python -m oracle.agent query "Find EDM remixes of Punk tracks"
python -m oracle.agent fact <track_id>
```

---

## ðŸ› Troubleshooting

**ModuleNotFoundError:** `pip install -r requirements.txt`  
**ChromaDB issues:** `python -m oracle.repair repair`  
**Server won't start:** `taskkill /F /IM python.exe` or use different port  
**Slow indexing:** Reduce batch size, use GPU if available  
**SQLite threading errors:** Fixed in v10 - upgrade if seeing thread-safety issues  
**Pipeline jobs stuck:** Check `.state` field in DB: `SELECT * FROM pipeline_jobs ORDER BY created_at DESC LIMIT 5`  
**Undo not working:** Check journal: `lyra history 10`

Check `logs/` directory for detailed error logs.

### Thread-Safety (v10)
All database operations now use thread-local connections for multi-threaded Flask compatibility. Validated under 20+ concurrent requests. See [THREAD_SAFETY_VALIDATION.md](THREAD_SAFETY_VALIDATION.md) for details.

---

## ðŸ“Š Performance

| Operation | Speed | Notes |
|-----------|-------|-------|
| File scan | ~1000 files/sec | Filesystem |
| CLAP embedding | ~5-10 tracks/sec | CPU only |
| Semantic search | ~50ms | 10K embeddings |
| Vibe build | ~100ms | 200 tracks |

**Tested:** Library-scale indexing with CLAP embeddings

---

## ðŸ—ºï¸ Roadmap

**Phase 1-8:** Foundation â†’ Sentient Core âœ… Complete  
**Phase 9-10:** Sentient Oracle + Safety Doctrine âœ… Complete  
**Phase 11:** Advanced Features
- [ ] Optional UI restoration (if desired) + WebSocket real-time updates
- [ ] Spotify Web Playback SDK integration
- [ ] Advanced constellation visualization (force-directed graphs)
- [ ] Multi-user authentication

**Phase 12:** Production Scale
- [ ] PostgreSQL support for large libraries (1M+ tracks)
- [ ] Distributed ChromaDB for horizontal scaling

---

## ðŸ“„ License

MIT License

---

## ðŸ™ Acknowledgments

**CLAP** â€¢ **ChromaDB** â€¢ **yt-dlp** â€¢ **Flask** â€¢ **Bootstrap**

Built with â¤ï¸ for music lovers who want to truly own their collection.

---

ðŸ“¬ **Issues:** GitHub Issues | **Discussions:** GitHub Discussions

ðŸŽµ **Happy Listening!**





---

## 2026-02-27 Operational Addendum

This section documents the latest queue/acquisition/scoring hardening.

- Waterfall order is now:
  - `T1` Qobuz
  - `T2` Streamrip (promoted fallback)
  - `T3` Slskd
  - `T4` Prowlarr + Real-Debrid
  - `T5` SpotDL
- Queue execution supports source targeting (`playlist`, `liked`, `top_tracks`, `history`) and priority ordering.
- Enrichment providers now include:
  - `musicbrainz`, `acoustid`, `discogs`, `lastfm`, `genius`
  - `acousticbrainz` (Essentia-derived high-level descriptors)
  - `musicnn` (optional local neural tag inference; set `MUSICNN_ENABLED=1`)
- Score validation now includes tag-alignment checks in `oracle score-audit`.
- Streamrip (`T2`) requires at least one configured source in `%APPDATA%\\streamrip\\config.toml`
  (Qobuz/Deezer/SoundCloud). If not configured, it fails fast and waterfall continues to `T3+`.

Recommended adjacent throughput mode:

```powershell
# Terminal A
python -m oracle drain --limit 50 --max-tier 5 --workers 6

# Terminal B
python -m oracle watch --once
python -m oracle score --all
```

Recommended validation sequence:

```powershell
python -m oracle.cli status
python -m oracle.cli score-audit
python -m pytest -q
```
