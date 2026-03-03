# CLAUDE.md — Lyra Oracle Project Instructions

## WHAT THIS IS

Lyra Oracle: AI-powered music intelligence system. Transforms Spotify listening history into a locally-owned, semantically searchable, emotionally intelligent music archive. Runs on Windows gaming rig (AMD Ryzen 7 7800X3D, AMD Radeon RX 9070 XT 16GB, 32GB RAM, 8TB A: drive). Project root: `C:\MusicOracle`.

Owner (Chris) is a novice programmer with professional ambitions. Write code he can read, run, and trust.

## THREE HATS — EVERY DECISION PASSES THROUGH ALL THREE

**Curator** — Library quality is sacred. Karaoke tracks, tribute bands, mislabeled rips get rejected. The acquisition guard (`oracle/acquirers/guard.py`) is the immune system — never weaken it.

**Programmer** — Production code. Full files, no placeholders. Type hints, docstrings, parameterized SQL. Test what you build.

**Mystic** — The 10-dimensional emotional model is the differentiator. Protect it. Feed it. The `track_scores` table MUST have data or everything downstream is decorative.

## CURRENT STATE (as of Feb 2026)

### What works:
- Full CLI with 30+ commands (argparse-based, `oracle/cli.py`)
- CLAP embeddings generating with music-specific model (`laion/larger_clap_music`) via DirectML (AMD GPU)
- ChromaDB vector storage in `chroma_storage/`
- **5-tier acquisition waterfall: Qobuz → Streamrip → Slskd (Soulseek) → Real-Debrid → SpotDL**
- Qobuz hi-fi acquisition: FLAC up to 24-bit/96kHz with full metadata + cover art
- Qobuz Docker microservice (`docker/qobuz/`) + direct `qobuz-dl` backend
- Acquisition guard with pre-flight/post-flight validation (duplicate detection working)
- Vibes system: save, materialize (hardlink), build M3U8, refresh, delete
- Curation: classify, plan, apply, undo workflow
- Download processor: list, clean filenames, organize into library
- Semantic search via CLAP text-to-audio similarity
- Auto-score on ingest (indexer triggers scorer)
- `oracle status` command shows full system state
- `oracle doctor` runs diagnostics
- Radio modes: Chaos, Flow, Discovery
- Taste learning from playback signals
- Pipeline verified end-to-end: scan → index → score (737 tracks, 736 embedded+scored)

### Current numbers (as of Feb 27, 2026):
- **tracks**: 2,472 | **embeddings**: 2,472 | **track_scores**: 2,472
- **acquisition_queue**: 0 pending (23,192 total processed)
- **playback_history**: 0
- Layers 1-4 healthy; LM Studio [OK]; all Docker services [OK]

### Root-level script sprawl:
Scripts at project root that should be in `scripts/` or `_archive/`:
`lyra_api.py`, `spotify_import.py` — these stay at root (imported by cli.py / importers)
`oracle.bat`, `lyra.bat` — Windows launchers, stay at root

## FIRST ACTION IN ANY SESSION

Run state audit. Report findings BEFORE proposing work.

```python
# Quick state check
from oracle.db.schema import get_connection
conn = get_connection()
c = conn.cursor()
tables = ["tracks", "track_scores", "embeddings", "spotify_history",
          "spotify_library", "acquisition_queue", "playback_history", "vibe_profiles"]
for t in tables:
    try:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"{t}: {c.fetchone()[0]}")
    except: print(f"{t}: MISSING")
conn.close()
```

Or just: `oracle status`

If track_scores is empty or far behind tracks count → that's today's priority.

## DEPENDENCY CHAIN — NEVER SKIP A LAYER

```
Layer 0: Infrastructure — .env, Python 3.12, .venv, A: drive, Docker (for Prowlarr, Qobuz, slskd)
Layer 1: Data — lyra_registry.db schema, tracks populated, spotify data imported
Layer 2: Embeddings — CLAP on DirectML (AMD GPU), ChromaDB populated, search returns results
Layer 3: Scores — track_scores populated for ALL tracks (736/737 ✓)
Layer 4: Acquisition — Qobuz → Streamrip → Slskd → RD → SpotDL waterfall, guard validates everything
Layer 5: Playback — foobar2000 + BeefWeb bridge, playback events → taste learning
Layer 6: Intelligence — Radio, Playlust arcs, taste profiles, discovery
```

Fix the lowest broken layer first. Always.

## ACTUAL FILE STRUCTURE

```
C:\MusicOracle\
├── oracle/                          # Main package (mostly flat)
│   ├── __init__.py, __main__.py
│   ├── cli.py                       # Argparse CLI — 30+ commands
│   ├── config.py                    # Config source (.env via dotenv)
│   ├── db/
│   │   ├── schema.py                # Schema + get_connection() + migrations
│   │   └── migrations/
│   ├── acquirers/
│   │   ├── guard.py                 # Pre-flight acquisition validation
│   │   ├── guarded_import.py        # Import with guard protection
│   │   ├── qobuz.py                 # Tier 1: Qobuz hi-fi (qobuz-dl backend)
│   │   ├── realdebrid.py            # Tier 3: Direct RD API
│   │   ├── prowlarr_rd.py           # Prowlarr search (used by RD tier)
│   │   ├── waterfall.py             # Unified T1→T2→T3→T4→T5 cascade
│   │   ├── smart_pipeline.py        # Smart acquisition with validation
│   │   ├── spotdl.py                # Tier 4: YouTube fallback
│   │   ├── validator.py             # Post-acquisition validation
│   │   └── ytdlp.py                 # YouTube download
│   ├── embedders/
│   │   └── clap_embedder.py         # CLAP with music model + fallback
│   ├── enrichers/                   # MusicBrainz, Last.fm, Genius, Discogs
│   ├── importers/                   # Spotify import
│   ├── scorer.py                    # 10-dimensional CLAP anchor scoring
│   ├── anchors.py                   # Text-phrase anchors per dimension
│   ├── taste.py                     # Playback → taste profile
│   ├── search.py                    # Semantic search
│   ├── scanner.py                   # Library file scanner
│   ├── indexer.py                   # Embed + auto-score
│   ├── radio.py                     # Smart Radio (Chaos/Flow/Discovery)
│   ├── arc.py                       # Emotional journey sequencer
│   ├── vibes.py                     # Vibe folders (hardlink)
│   ├── classifier.py                # Track quality classification
│   ├── curator.py                   # Plan/apply/undo curation
│   ├── doctor.py                    # System diagnostics
│   ├── audit.py                     # Database audit
│   ├── normalizer.py                # Metadata normalization
│   ├── name_cleaner.py              # Filename cleaning
│   ├── download_processor.py        # Downloads management
│   ├── agent.py                     # LLM agent interface
│   ├── llm.py                       # LLM provider (LM Studio / Ollama)
│   ├── lyra_protocol.py             # Unified acquisition protocol
│   ├── chroma_store.py              # ChromaDB wrapper
│   ├── pipeline.py                  # Scan→index→score pipeline
│   ├── bootstrap.py                 # LM Studio + Docker auto-start
│   ├── catalog.py                   # MusicBrainz catalog lookup/acquire
│   ├── ops.py                       # Operational utilities
│   ├── safety.py                    # Journal/undo (used by Flask + console)
│   ├── validation.py                # Validation rules (used by Flask)
│   ├── fast_batch.py                # Fast batch download (used by Flask)
│   └── [scout.py, lore.py, dna.py, hunter.py, architect.py, console.py]
├── docker/
│   └── qobuz/                       # Qobuz microservice (Dockerfile + FastAPI)
│       ├── Dockerfile
│       ├── service.py               # FastAPI: /health, /acquire, /acquire/batch, /search
│       └── requirements.txt
├── data/, chroma_storage/, hf_cache/, logs/, library/, staging/, downloads/
├── Lyra_Oracle_System/              # Prowlarr config files (mounted by docker-compose)
├── .env, .env.template, .gitignore
├── lyra_registry.db
├── spotify_import.py
├── lyra.ps1, Launch-Lyra.ps1
├── requirements.txt, README.md
└── _archive/                        # Stale files go here
```

## THE 10 DIMENSIONS (from anchors.py — THESE ARE THE REAL ONES)

```
energy:     ambient/still ←→ explosive/driving
valence:    sad/hopeless ←→ ecstatic/euphoric
tension:    relaxed/resolved ←→ horror/panic/dissonant
density:    solo/bare ←→ massive/wall-of-sound
warmth:     cold/robotic ←→ warm/analog/soulful
movement:   frozen/drone ←→ driving/groove/danceable
space:      intimate/dry ←→ vast/cathedral/oceanic
rawness:    polished/pristine ←→ distorted/lo-fi/garage
complexity: simple/repetitive ←→ progressive/virtuosic
nostalgia:  modern/futuristic ←→ retro/vintage/throwback
```

NOTE: Previous docs said "darkness" and "transcendence" — those DON'T EXIST in anchors.py. The actual dimensions are **valence** and **density**. Always match the code.

## ACQUISITION WATERFALL (ACTUAL — 5 TIERS)

```
Tier 1: Qobuz (qobuz-dl)        — FLAC up to 24-bit/96kHz, full metadata + cover art
Tier 2: Streamrip               — alternative hi-fi ripper fallback (if configured)
Tier 3: Slskd (Soulseek)        — FLAC from P2P, ~10-30s/track, ~90% hit rate
Tier 4: Real-Debrid + Prowlarr  — FLAC albums, direct HTTPS download
Tier 5: SpotDL                   — YouTube Music fallback (~256kbps)
```

### Qobuz Details:
- **Backend**: `qobuz-dl` library (pip install qobuz-dl)
- **Auth**: Auto-extracts `app_id` + secrets from Qobuz web bundle JS — only needs `QOBUZ_USERNAME` + `QOBUZ_PASSWORD`
- **Quality IDs**: 5=MP3 320k, 6=FLAC 16/44.1 (CD), 7=FLAC 24/96 (hi-res default), 27=FLAC 24/192
- **Docker service**: `lyra_qobuz` container on port 7700, FastAPI with `/health`, `/acquire`, `/acquire/batch`, `/search`
- **Direct mode**: `oracle/acquirers/qobuz.py` — `QobuzAcquirer` class, falls back from Docker service to direct qobuz-dl
- **Album downloads**: Use `qobuz-dl` CLI or script for bulk album acquisition (tested: Brand New full discography, 60 FLACs, 2.57 GB)
- **Match threshold**: SequenceMatcher score >= 0.55 (0.4 artist weight + 0.6 title weight)
- **Cover art**: Downloads cover.jpg, embeds into FLAC via mutagen, then deletes cover.jpg

Authoritative runtime path is `oracle/acquirers/smart_pipeline.py` delegating
to `oracle/acquirers/waterfall.py`. `oracle/pipeline.py` and `oracle/console.py`
exist as compatibility wrappers.

## .ENV — KNOWN ISSUES

Template consolidated to single canonical keys (Feb 2026):
- `LIBRARY_BASE` (was also `LIBRARY_DIR` — config.py still accepts both as fallback)
- `DOWNLOADS_FOLDER` (was also `DOWNLOAD_DIR`)
- `CHROMA_PATH` (was also `CHROMA_DIR`)
- `REAL_DEBRID_KEY` (was also `REALDEBRID_API_KEY`)
- `GENIUS_TOKEN` (was also `GENIUS_ACCESS_TOKEN`)
- `DISCOGS_API_TOKEN` (was also `DISCOGS_TOKEN`)

config.py still accepts the old names as fallbacks, but `.env.template` only lists the canonical keys.

### Qobuz .env Keys:
```
QOBUZ_USERNAME=<email>          # Qobuz account email
QOBUZ_PASSWORD=<password>       # Qobuz account password
QOBUZ_QUALITY=7                 # 5=MP3, 6=FLAC CD, 7=FLAC 24/96, 27=FLAC 24/192
QOBUZ_SERVICE_URL=http://localhost:7700  # Docker microservice URL
```
Note: `QOBUZ_APP_ID` and `QOBUZ_APP_SECRET` are NOT needed — auto-extracted by qobuz-dl.

LLM provider is LM Studio with qwen2.5-14b-instruct (not Ollama/llama3).

## KNOWN BUGS — FIX ON ENCOUNTER

1. ~~**Duplicate get_connection()**~~ — FIXED: config.py delegates to db/schema.py
2. **Root-level script sprawl** — 15+ scripts should be in `scripts/` or `_archive/`
3. ~~**Hardcoded paths**~~ — FIXED: curator.py, organizer.py, download_processor.py now use config.LIBRARY_BASE
4. **Browser audio** — preferred codec is m4a/256k (browser-compatible), but verify FLAC files get transcoded if served via Flask
5. ~~**.env key duplication**~~ — FIXED: template consolidated to single keys (GENIUS_TOKEN, REAL_DEBRID_KEY, LIBRARY_BASE, CHROMA_PATH)
6. **Symlink fallback** — hardlinks only on Windows (no admin needed)
7. ~~**`Lyra_Oracle_System/`**~~ — NOT a duplicate. Contains Prowlarr config files mounted by docker-compose. Leave it.

## CODING STANDARDS

- snake_case.py, snake_case(), PascalCase, UPPER_SNAKE
- Type hints on all signatures, Google docstrings
- `pathlib.Path` always, never `os.path`
- `logging.getLogger(__name__)`, not print()
- Parameterized SQL only (`?` placeholders)
- All paths from config.py
- stdlib → third-party → local imports

## CLI REFERENCE (argparse, NOT Click)

```bash
oracle status                    # System state
oracle doctor                    # Diagnostics
oracle scan --library "A:\..."   # Scan audio files
oracle index --library "A:\..."  # Embeddings + auto-score
oracle search --query "dark ambient" --n 10
oracle score --all               # Score ALL tracks
oracle pipeline --library "A:\..." # Scan + index + score
oracle acquire waterfall --artist X --title Y
oracle drain --limit N [--max-tier 4] [--workers 3]  # Drain queue + auto-ingest
                                 # --no-ingest to skip embed/score after download
oracle guard test --artist X --title Y
oracle guard import --downloads downloads
oracle watch [--once]            # Ingest watcher: staging/ → library
oracle vibe save --name "Late Night" --query "dark ambient"
oracle vibe materialize --name "Late Night" --mode hardlink
oracle curate classify
oracle downloads organize --library "A:\..."
oracle serve --port 5000
oracle smart-acquire --artist X --title Y
oracle normalize --apply
oracle enrich-all
oracle played --artist X --title Y [--skipped] [--weight N]  # Manual taste signal
oracle listen [--host H] [--port P]  # BeefWeb bridge for foobar2000
oracle catalog lookup --artist X     # MusicBrainz catalog lookup
oracle catalog acquire --artist X    # Full discography acquisition
```

## AUTONOMOUS OPERATION

**Keep going:** fixing imports, __init__.py, error handling, snake_case, hardcoded paths, tests, missing dirs

**Stop and ask:** schema changes that drop data, architecture changes, A: drive structure, RD quota spending, ambiguous choices

**Log:** `[DECISION] what [REASON] why [VERIFIED] how confirmed`

## SESSION WORKFLOW

1. **Orient** — `oracle status`, report numbers
2. **Identify** — lowest broken layer in dependency chain
3. **Build** — fix it, test each change
4. **Verify** — re-run status, compare before/after
5. **Handoff** — changes, next priority, issues

## WHAT DONE LOOKS LIKE

- [x] track_scores count matches tracks count (2,472/2,472)
- [x] `oracle search` returns sensible, differentiated results
- [x] `oracle acquire waterfall` completes end-to-end (5-tier: Qobuz→Streamrip→Slskd→RD→SpotDL)
- [x] Qobuz acquirer downloads hi-fi FLAC with full metadata
- [x] No duplicate get_connection() — config.py delegates to db/schema.py
- [x] Single .env keys (no duplicates) — template consolidated
- [x] No hardcoded paths — curator/organizer/download_processor use config.LIBRARY_BASE
- [x] `oracle drain` auto-ingests (embed+score) — no manual `watch --once` needed
- [x] `oracle hunt` routes directly through SmartAcquisition (pipeline.py decoupled from CLI)
- [x] `oracle batch run` removed (superseded by `oracle drain`)
- [x] `generate_target_path` moved to curator.py — organizer import removed
- [x] `fast_batch.py` uses YTDLPAcquirer — downloader.py dependency removed
- [ ] `oracle serve` → browser plays audio
- [ ] Playback events flowing via foobar2000 + BeefWeb
- [ ] Root dir has <10 non-config files

## DOCKER SERVICES

```bash
docker-compose up -d             # Start all services
docker-compose ps                # Check status
```

| Service   | Container        | Port  | Purpose                          |
|-----------|-----------------|-------|----------------------------------|
| prowlarr  | lyra_prowlarr   | 9696  | Torrent indexer (for RD tier)    |
| rdtclient | lyra_rdtclient  | 6500  | Real-Debrid download manager     |
| qobuz     | lyra_qobuz      | 7700  | Qobuz hi-fi acquisition API      |
| slskd     | lyra_slskd      | 5030  | Soulseek P2P client              |
