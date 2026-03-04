# 🎵 Lyra Oracle: AI-Powered Music Intelligence System

**Lyra Oracle** is a locally-owned, semantically searchable, emotionally intelligent music archive. It transforms Spotify listening history into a 10-dimensional cultural understanding of your taste, powered by CLAP embeddings and a suite of intelligence modules (Scout, Lore, DNA, Architect, Radio).

**Current State (March 2026):** 60% toward "Oracle of Culture" vision. Full semantic search, vibe system, and acquisition pipeline operational. Missing: Biographer module, live Constellation, Artist Shrines, Playlust automation.

## ✨ Core Features

| Feature | Status | Use Case |
|---------|--------|----------|
| **Semantic Search** | ✅ Live | "dark ambient with glitchy textures" → finds exact matches |
| **CLAP Embeddings** | ✅ Live | 512-dim music-specific embeddings (DirectML on AMD GPU) |
| **Vibe System** | ✅ Live | Save/build/materialize semantic playlists as hardlinked folders |
| **Curation** | ✅ Live | Classify, plan, apply library organization workflows |
| **4-Tier Acquisition** | ✅ Live | Qobuz (hi-fi) → Slskd → Real-Debrid → SpotDL |
| **Scout** (Discovery) | ✅ Live | Cross-genre bridge artist finding |
| **Lore** (Lineage) | ✅ Live | Artist relationship mapping (MusicBrainz-backed) |
| **DNA** (Samples) | ✅ Live | Sample origin tracing |
| **Architect** (Structure) | ✅ Live | BPM, key, drop detection, energy profiles |
| **Radio** (Playback) | ✅ Live | Chaos/Flow/Discovery playback modes |
| **Flask API + Web UI** | ✅ Live | 21+ endpoints, responsive dashboard |
| **Biographer** (Context) | ❌ Missing | Artist bios, imagery, scene context |
| **Constellation** (Visual) | ⚠️ Mock Data | Artist relationship network (component exists, needs live backend) |
| **Playlust** (Automation) | ❌ Missing | Auto-generate 4-act emotional journeys with reasoning |

## 🛠️ Requirements

- **Windows 10/11** (gaming rig optimal: AMD Ryzen 7 7800X3D, AMD Radeon RX GPU, 32GB RAM)
- **Python 3.12+** (in `.venv`, NOT system Python 3.14)
- **Node.js 20+** (for desktop app)
- **SQLite** (bundled)
- **Docker Desktop** (for Qobuz/Prowlarr/slskd services, optional)
- **LM Studio** with `qwen2.5-14b-instruct` (for LLM features)

Optional but recommended:
- **Qobuz** account (hi-fi music acquisition)
- **Real-Debrid** API key (album torrent downloads)
- **Prowlarr** (torrent indexing)
- **foobar2000 + BeefWeb** (playback integration)

## 📁 Repository Layout

```
C:\MusicOracle/
├── oracle/                          # Main Python package (ML + intelligence)
│   ├── cli.py                       # 30+ argparse commands
│   ├── config.py                    # .env configuration
│   ├── searcher.py                  # Semantic search engine
│   ├── scorer.py                    # 10-dimensional emotional scoring
│   ├── anchors.py                   # Dimension definitions (energy, valence, etc.)
│   ├── acquirers/                   # 4-tier acquisition waterfall
│   │   ├── qobuz.py                 # Tier 1: Hi-fi FLAC (24-bit/96kHz)
│   │   ├── waterfall.py             # Unified T1→T2→T3→T4 cascade
│   │   ├── guard.py                 # Acquisition validation (duplicate detection)
│   │   └── validator.py             # Post-download validation
│   ├── embedders/                   # CLAP embeddings (DirectML)
│   ├── enrichers/                   # Metadata enrichment (Last.fm, Genius, MusicBrainz)
│   ├── db/
│   │   ├── schema.py                # SQLite schema (16 tables)
│   │   └── migrations/
│   ├── scout.py                     # Cross-genre discovery intelligence
│   ├── lore.py                      # Artist lineage mapping
│   ├── dna.py                       # Sample origin tracing
│   ├── architect.py                 # Audio structure analysis
│   ├── radio.py                     # Chaos/Flow/Discovery modes
│   ├── agent.py                     # LLM orchestration
│   ├── vibes.py                     # Semantic playlist management
│   ├── pipeline.py                  # Scan → Index → Score workflow
│   └── [30+ other modules]
├── desktop/                         # Electron frontend (React + Vite)
│   ├── renderer-app/src/
│   │   ├── features/                # Feature components
│   │   │   ├── library/             # LibraryView, ArtistShrine (WIP)
│   │   │   ├── search/              # SemanticSearch
│   │   │   ├── oracle/              # ConstellationScene (mock → live)
│   │   │   ├── radio/               # RadioEngine controls
│   │   │   └── vibes/               # VibePlaylists
│   │   └── services/
│   │       └── lyraGateway/         # API client
│   ├── package.json
│   └── vite.config.ts
├── docker/
│   ├── qobuz/                       # Qobuz acquisition microservice
│   └── docker-compose.yml           # All services (Prowlarr, slskd, RDT, Qobuz)
├── chroma_storage/                  # ChromaDB vector store (HNSW index)
├── lyra_registry.db                 # SQLite database
├── lyra_api.py                      # Flask API server (main entry point)
├── requirements.txt                 # Python dependencies
├── .env.template                    # Configuration template
└── docs/
    ├── MASTER_PLAN_EXPANDED.md      # Complete feature roadmap (THIS FILE)
    ├── MISSING_FEATURES_REGISTRY.md # All 16 missing features w/ specs
    └── specs/
```

## 🚀 Quick Start

### 1. Setup Python Environment

```powershell
cd C:\MusicOracle
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env
```

### 2. Configure `.env`

```bash
# Required
LIBRARY_BASE=A:\music\Active Music
QOBUZ_USERNAME=your_qobuz_email
QOBUZ_PASSWORD=your_qobuz_password
REAL_DEBRID_KEY=your_rd_api_key

# Optional enrichment APIs
LASTFM_API_KEY=
GENIUS_TOKEN=
DISCOGS_API_TOKEN=
THEAUDIODB_API_KEY=

# LLM
LYRA_LLM_PROVIDER=local
LYRA_LLM_BASE_URL=http://127.0.0.1:1234/v1
LYRA_LLM_MODEL=qwen2.5-14b-instruct
```

### 3. Start Services

```powershell
# Start Docker services (Qobuz microservice, Prowlarr, slskd, etc.)
docker-compose up -d

# Start LM Studio on port 1234 (manual or via bootstrap)
# Then start Flask API
.venv\Scripts\python.exe lyra_api.py
# OR: oracle serve --port 5000
```

### 4. Run CLI Commands

```bash
# Scan library for audio files
oracle scan --library "A:\music\Active Music"

# Generate CLAP embeddings + auto-score
oracle index --library "A:\music\Active Music"

# Semantic search
oracle search --query "dark ambient with glitchy textures" --n 10

# Create vibe (semantic playlist)
oracle vibe save --name "Late Night" --query "dark moody introspective" --n 50

# Materialize vibe as hardlinked folder
oracle vibe materialize --name "Late Night" --mode hardlink

# Check system status
oracle status

# Full diagnostics
oracle doctor
```

## 🎯 10-Dimensional Emotional Model

Every track is scored on these dimensions (0.0–1.0):

| Dimension | Low (0.0) | High (1.0) |
|-----------|-----------|-----------|
| **energy** | ambient, still | explosive, driving |
| **valence** | sad, hopeless | ecstatic, euphoric |
| **tension** | relaxed, resolved | horror, panic, dissonant |
| **density** | solo, bare | massive, wall-of-sound |
| **warmth** | cold, robotic | warm, analog, soulful |
| **movement** | frozen, drone | driving, groove, danceable |
| **space** | intimate, dry | vast, cathedral, oceanic |
| **rawness** | polished, pristine | distorted, lo-fi, garage |
| **complexity** | simple, repetitive | progressive, virtuosic |
| **nostalgia** | modern, futuristic | retro, vintage, throwback |

These power semantic search, radio modes, taste learning, and playlist generation.

## 🎵 The 4-Tier Acquisition Waterfall

Lyra tries each tier in sequence until a match is found:

```
Tier 1: Qobuz          → FLAC 24-bit/96kHz + hi-fi metadata
Tier 2: Slskd (P2P)    → FLAC from Soulseek (~10-30s/track, 90% hit rate)
Tier 3: Real-Debrid    → Album torrents via Prowlarr search
Tier 4: SpotDL         → YouTube Music (~256kbps fallback)
```

Each tier validates against the acquisition guard (duplicate detection, format verification).

## 🧠 Intelligence Modules

| Module | Purpose | Status |
|--------|---------|--------|
| **Scout** | Find bridge artists between genres | ✅ Functional |
| **Lore** | Artist lineage + relationships (MusicBrainz) | ✅ Functional |
| **DNA** | Sample origin tracing | ✅ Functional |
| **Architect** | Audio structure analysis (BPM, key, drops) | ✅ Functional |
| **Radio** | Chaos/Flow/Discovery playback modes | ✅ Functional |
| **Biographer** | Artist bios + cultural context | ❌ Not built |
| **Pathfinder** | Interactive relationship exploration | ⚠️ Partial (API exists, no UI) |

## 📊 Current Numbers (March 2, 2026)

```
Tracks:              2,472
Embeddings:          2,472 (100% coverage)
Track Scores:        2,472 (10-dimensional scoring complete)
Vibes:               15 saved
Acquisition Queue:   0 (all processed)
Connections:         847 artist relationships mapped
```

## 🛠️ Common Commands

```bash
# Library operations
oracle scan --library "A:\music\Active Music"   # Find audio files
oracle index --library "A:\music\Active Music"  # Generate embeddings
oracle pipeline --library "A:\music"            # Scan → Index → Score (all-in-one)

# Semantic search
oracle search --query "aggressive distorted guitars" --n 20
oracle search --query "chill lo-fi beats" --n 50

# Vibe management
oracle vibe save --name "Workout" --query "high energy"
oracle vibe build --name "Workout"              # Generate M3U8
oracle vibe materialize --name "Workout"        # Create hardlinked folder
oracle vibe refresh --all                       # Update all vibes

# Acquisition
oracle acquire waterfall --artist "Radiohead" --title "Pyramid Song"
oracle drain --limit 10 --workers 3             # Process queue + ingest
oracle watch --once                             # One-time staging folder ingest

# Curation workflow
oracle curate classify                          # Classify library tracks
oracle curate plan --preset artist_album        # Generate organization plan
oracle curate apply                             # Apply plan with confirmation

# System health
oracle status                                   # Show library statistics
oracle doctor                                   # Run comprehensive diagnostics
```

## 🌐 Flask API (Web UI)

Access at `http://localhost:5000` when server running.

**Key Endpoints:**
- `GET /api/status` — System statistics
- `POST /api/search` — Semantic search with result limit
- `GET /api/vibes` — List all saved vibes
- `POST /api/vibes/save` — Create vibe from query
- `POST /api/vibes/build` — Generate M3U8 playlist
- `POST /api/vibes/materialize` — Create hardlinked folder
- `POST /api/curate/classify` — Classify tracks
- `POST /api/curate/plan` — Generate curation plan
- `POST /api/curate/apply` — Apply curation plan
- `POST /api/acquire/youtube` — Download from YouTube
- `GET /api/scout/cross-genre` — Cross-genre discovery
- `GET /api/lore/connections` — Artist relationships
- `GET /api/radio/chaos` — Next track (Chaos mode)
- `GET /api/radio/flow` — Next track (Flow mode)

## 🧪 Testing & Diagnostics

### Health Checks

```powershell
# Check LLM configuration
powershell -ExecutionPolicy Bypass -File .\scripts\check_llm_config.ps1

# Run smoke tests
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_desktop.ps1

# Full system diagnostics
oracle doctor
```

### Run Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

### Build Desktop

```powershell
cd C:\MusicOracle\desktop
npm install
npm run dev                  # Development server
npm run build               # Production build
```

## 📖 Documentation

- **[docs/MASTER_PLAN_EXPANDED.md](docs/MASTER_PLAN_EXPANDED.md)** — Complete roadmap (60% → 100%)
- **[docs/specs/SPEC-001.md](docs/specs/SPEC-001.md)** — Database schema + API contract
- **[docs/specs/SPEC-002.md](docs/specs/SPEC-002.md)** — Playlust vision + emotional arc design

## 🗺️ Development Roadmap

**Next Priority (Sprints 1-2):**
1. **Biographer module** — Artist bios + imagery (2-3 weeks)
2. **Graph auto-builder** — Proactive relationship mapping (1 week)
3. **Constellation live data** — Make visual network real (1 week)
4. **Artist Shrines** — Rich artist profile UI (2-3 weeks)

**Near-term (Sprints 3-4):**
5. **Deep Cut protocol** — High acclaim / low popularity discovery (2 weeks)
6. **Playlust MVP** — Automated 4-act emotional journeys (3-4 weeks)

**See [docs/MASTER_PLAN_EXPANDED.md](docs/MASTER_PLAN_EXPANDED.md) for full 16-feature roadmap + effort estimates.**

## 🤝 Contributing

This is an active research project. All contributions welcome. Please:
1. Follow existing code patterns (snake_case, type hints, docstrings)
2. Test locally before committing
3. Update docs if adding new features

## 📄 License

Lyra Oracle © 2025-2026. All rights reserved.

- `GET /api/health`
- `GET /api/vibes`
- `GET /api/playlists/<playlist_id>`
- `GET /api/library/tracks`
- `POST /api/search`
- `POST /api/radio/chaos`
- `POST /api/radio/flow`
- `GET /api/radio/discovery`
- `POST /api/radio/queue`
- `GET /api/tracks/<track_id>/dossier`
- `GET /api/stream/<track_id>`
