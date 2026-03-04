# MEMORY.md — Lyra Oracle Live State

> **Agents: Read this file at the start of every session. Update it after every batch of changes.**
> Numbers here are the source of truth — all other docs go stale.

---

## SYSTEM HEALTH (last updated: 2026-03-04)

**Overall status:** Layers 1–4 healthy; playback (Layer 5) not yet wired.

| Layer | Name          | Status  | Notes                                              |
|-------|---------------|---------|----------------------------------------------------|
| 0     | Infrastructure | ✅ OK  | Python 3.12, .venv, A: drive, Docker services up  |
| 1     | Data           | ✅ OK  | lyra_registry.db populated, Spotify data imported |
| 2     | Embeddings     | ✅ OK  | CLAP (DirectML), ChromaDB populated               |
| 3     | Scores         | ✅ OK  | track_scores matches tracks count                 |
| 4     | Acquisition    | ✅ OK  | 5-tier waterfall operational                      |
| 5     | Playback       | ⚠️ TODO | foobar2000 + BeefWeb bridge not connected        |
| 6     | Intelligence   | ⚠️ TODO | Radio/Playlust/discovery partially wired         |

---

## CURRENT METRICS

| Table               | Count   | Notes                                  |
|---------------------|---------|----------------------------------------|
| tracks              | 2,472   |                                        |
| embeddings          | 2,472   | All tracks embedded                    |
| track_scores        | 2,472   | All tracks scored (10 dimensions)      |
| acquisition_queue   | 0       | 23,192 total processed                 |
| playback_history    | 0       | Playback bridge not yet connected      |
| spotify_history     | —       | Imported                               |
| vibe_profiles       | —       | Active                                 |

---

## WHAT WORKS

- Full CLI (`oracle/cli.py`) — 30+ commands
- CLAP embeddings via `laion/larger_clap_music` + DirectML (AMD GPU)
- ChromaDB vector search in `chroma_storage/`
- 5-tier acquisition waterfall: Qobuz → Streamrip → Slskd → Real-Debrid → SpotDL
- Qobuz Docker microservice (port 7700) — FLAC up to 24-bit/96kHz
- Acquisition guard: pre-flight + post-flight validation (duplicate detection)
- Vibes: save, materialize (hardlink), build M3U8, refresh, delete
- Curation: classify → plan → apply → undo workflow
- Download processor: list, clean filenames, organize into library
- Semantic search (CLAP text-to-audio similarity)
- Auto-score on ingest (indexer triggers scorer)
- `oracle status` and `oracle doctor` commands
- Radio modes: Chaos, Flow, Discovery
- Taste learning from playback signals
- Pipeline verified end-to-end: scan → index → score
- React 18 + TypeScript frontend (Vite, TanStack Router/Query, Zustand, Framer Motion)
- Unified CSS design system: dark-blue + lime aesthetic (amber/blue conflict removed)
- OracleDiscoveryPanel, DimensionalSearchPanel wired in frontend
- Artist route, Home route, Oracle route in frontend

## WHAT IS BROKEN / IN PROGRESS

- `oracle serve` → browser plays audio (not verified)
- Playback events via foobar2000 + BeefWeb not flowing
- Root dir still has >10 non-config files (sprawl)
- LM Studio provider: qwen2.5-14b-instruct (verify connection on new session)

---

## NEXT PRIORITIES (in order)

1. **Playback bridge** — connect foobar2000 + BeefWeb (`oracle listen`) so `playback_history` populates
2. **Browser audio** — verify `oracle serve` serves FLAC/m4a playable in Electron frontend
3. **Root dir cleanup** — move stale scripts to `scripts/` or `_archive/`
4. **Taste profile loop** — verify playback → taste → radio recommendation cycle works end-to-end

---

## KEY FILE LOCATIONS

| Purpose               | Path                                        |
|-----------------------|---------------------------------------------|
| CLI entry             | `oracle/cli.py`                             |
| Config (source of truth) | `oracle/config.py`                       |
| DB schema + migrations | `oracle/db/schema.py`                      |
| Acquisition waterfall | `oracle/acquirers/waterfall.py`             |
| Acquisition guard     | `oracle/acquirers/guard.py`                 |
| 10-dim scorer         | `oracle/scorer.py`                          |
| Dimension anchors     | `oracle/anchors.py`                         |
| Flask app factory     | `oracle/api/__init__.py`                    |
| API blueprints        | `oracle/api/blueprints/`                    |
| Frontend root         | `desktop/renderer-app/`                     |
| Docker services       | `docker-compose.yml`, `docker/`             |

---

## THE 10 DIMENSIONS (canonical — from anchors.py)

```
energy     ambient/still ←→ explosive/driving
valence    sad/hopeless ←→ ecstatic/euphoric
tension    relaxed/resolved ←→ horror/panic/dissonant
density    solo/bare ←→ massive/wall-of-sound
warmth     cold/robotic ←→ warm/analog/soulful
movement   frozen/drone ←→ driving/groove/danceable
space      intimate/dry ←→ vast/cathedral/oceanic
rawness    polished/pristine ←→ distorted/lo-fi/garage
complexity simple/repetitive ←→ progressive/virtuosic
nostalgia  modern/futuristic ←→ retro/vintage/throwback
```

> NOTE: "darkness" and "transcendence" do NOT exist. The real dimensions are valence and density.

---

## DOCKER SERVICES

| Service   | Container       | Port  | Purpose                        |
|-----------|-----------------|-------|--------------------------------|
| prowlarr  | lyra_prowlarr   | 9696  | Torrent indexer (for RD tier)  |
| rdtclient | lyra_rdtclient  | 6500  | Real-Debrid download manager   |
| qobuz     | lyra_qobuz      | 7700  | Qobuz hi-fi acquisition API    |
| slskd     | lyra_slskd      | 5030  | Soulseek P2P client            |

---

## .ENV CANONICAL KEYS

```
LIBRARY_BASE          # (was also LIBRARY_DIR)
DOWNLOADS_FOLDER      # (was also DOWNLOAD_DIR)
CHROMA_PATH           # (was also CHROMA_DIR)
REAL_DEBRID_KEY       # (was also REALDEBRID_API_KEY)
GENIUS_TOKEN          # (was also GENIUS_ACCESS_TOKEN)
DISCOGS_API_TOKEN     # (was also DISCOGS_TOKEN)
QOBUZ_USERNAME
QOBUZ_PASSWORD
QOBUZ_QUALITY         # 5=MP3, 6=FLAC CD, 7=FLAC 24/96 (default), 27=FLAC 24/192
QOBUZ_SERVICE_URL     # http://localhost:7700
```

---

## KNOWN RESOLVED BUGS

- ~~Duplicate `get_connection()`~~ — FIXED: config.py delegates to db/schema.py
- ~~Hardcoded paths~~ — FIXED: curator.py, organizer.py, download_processor.py use config.LIBRARY_BASE
- ~~.env key duplication~~ — FIXED: template consolidated to single canonical keys

## KNOWN OPEN BUGS

- Root-level script sprawl (>10 non-config files at repo root)
- Browser audio: FLAC files may need transcoding when served via Flask
- Symlink fallback: hardlinks only (no admin needed on Windows)
