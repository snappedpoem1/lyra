# 🎵 Lyra Oracle

**AI-powered music intelligence system built on a Windows gaming rig.**

Turn a Spotify listening history into a locally-owned, semantically-searchable, emotionally-intelligent music archive. No subscriptions. No cloud. No bullshit.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Electron](https://img.shields.io/badge/desktop-electron-47848F.svg)](https://www.electronjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

- **Acquires music** — 4-tier waterfall: Qobuz hi-fi FLAC → Soulseek P2P → Real-Debrid → SpotDL YouTube fallback
- **Understands music** — CLAP (Contrastive Language-Audio Pretraining) embeddings, semantic search across 1,100+ tracks in ~50ms
- **Scores music emotionally** — 10-dimensional model (energy · valence · tension · density · warmth · movement · space · rawness · complexity · nostalgia)
- **Learns your taste** — playback signals feed a taste profile that shapes radio, discovery, and recommendations
- **Builds Vibes** — save a semantic query as a dynamic playlist that updates as your library grows
- **Runs smart radio** — Chaos (random exploration) · Flow (mood-matched continuity) · Discovery (stuff you haven't heard)
- **Desktop app incoming** — Neo-Winamp Electron UI in progress (albums/artists/visualizer/Lyra Bar)

---

## Hardware This Runs On

```
CPU: AMD Ryzen 7 7800X3D
GPU: AMD Radeon RX 9070 XT (16GB) — CLAP embeddings via ROCm/CUDA
RAM: 32GB
Storage: 8TB A: drive (music library)
OS: Windows 11
```

It will probably run on other setups but this is what it was built and tested on.

---

## Quick Start

**Double-click `boot_oracle.bat`** — it starts Docker Desktop (if needed), brings up all services, and optionally loads the LM Studio model.

Then in any terminal:

```bash
oracle status          # see what's running and how many tracks you have
oracle doctor          # diagnose if something looks wrong
oracle serve           # start the Flask API on localhost:5000
```

### First-Time Setup

```bash
# 1. Create virtual environment
py -3.12 -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in .env
copy .env.template .env
# edit .env with your paths, API keys, credentials

# 4. Initialize the database
oracle db migrate

# 5. Import your Spotify history (export from Spotify → drop in data/)
oracle import spotify --data-dir data/

# 6. Queue and acquire your library
oracle drain --limit 100 --workers 3 --max-tier 5
```

---

## Architecture

```
Layer 0: Infrastructure — Docker (Prowlarr · RD Client · Slskd · Qobuz), LM Studio
Layer 1: Data         — SQLite (lyra_registry.db), Spotify history imported
Layer 2: Embeddings   — CLAP on AMD GPU (ROCm), ChromaDB vector store
Layer 3: Scores       — 10-dim emotional scoring for every track
Layer 4: Acquisition  — 4-tier waterfall, acquisition queue, guard validation
Layer 5: Playback     — taste learning from play/skip signals
Layer 6: Intelligence — Radio, Vibes, semantic search, LLM agent
```

Fix the lowest broken layer first. Always.

---

## Acquisition Waterfall

```
Tier 1: Qobuz       — FLAC up to 24-bit/96kHz, full metadata + embedded art
Tier 2: Slskd       — Soulseek P2P, FLAC quality, ~90% hit rate
Tier 3: Real-Debrid — Cached torrents via Prowlarr + HTTPS download
Tier 4: SpotDL      — YouTube Music fallback (~256kbps)
```

```bash
oracle drain --limit 500 --workers 3 --max-tier 5   # drain the queue
oracle acquire waterfall --artist "Burial"           # one-off acquisition
oracle catalog acquire --artist "Portishead"         # full discography
```

---

## Core CLI Commands

```bash
# System
oracle status                              # counts: tracks, embeddings, scores, queue
oracle doctor                              # diagnose issues
oracle serve [--port 5000]                 # start Flask API

# Library
oracle scan --library "A:\music\Active Music"
oracle index --library "A:\music\Active Music"
oracle score --all                         # score any unscored tracks

# Search & Radio
oracle search --query "dark ambient" --n 20
oracle radio chaos --count 20
oracle radio flow --track-id 123 --count 20

# Vibes
oracle vibe save --name "Late Night" --query "dark minimal electronic"
oracle vibe materialize --name "Late Night" --mode hardlink

# Acquisition
oracle drain --limit 100 --workers 3 --max-tier 5
oracle acquire waterfall --artist X --title Y
oracle catalog acquire --artist "Artist Name"

# Taste learning
oracle played --artist X --title Y            # mark as played
oracle played --artist X --title Y --skipped  # mark as skipped
```

---

## Docker Services

```bash
docker compose up -d    # start all services
docker compose ps       # check status
```

| Service | Port | Purpose |
|---------|------|---------|
| Prowlarr | 9696 | Torrent indexer (for Real-Debrid tier) |
| RD Client | 6500 | Real-Debrid download manager |
| Qobuz | 7700 | Qobuz hi-fi acquisition API |
| Slskd | 5030 | Soulseek P2P client |

---

## The 10 Dimensions

Every track in the library gets scored on:

```
energy     — ambient/still ↔ explosive/driving
valence    — sad/hopeless  ↔ ecstatic/euphoric
tension    — relaxed       ↔ horror/panic/dissonant
density    — solo/bare     ↔ massive/wall-of-sound
warmth     — cold/robotic  ↔ warm/analog/soulful
movement   — frozen/drone  ↔ driving/groove/danceable
space      — intimate/dry  ↔ vast/cathedral/oceanic
rawness    — polished      ↔ distorted/lo-fi/garage
complexity — repetitive    ↔ progressive/virtuosic
nostalgia  — futuristic    ↔ retro/vintage/throwback
```

These power semantic search, radio, and the radar chart in the desktop app.

---

## LM Studio (Optional)

The agent feature uses a local LLM for natural language queries and playlist narration. Not required for core functionality.

- **Model:** Qwen2.5-14B-Instruct (recommended)
- **Server:** LM Studio on `localhost:1234`
- **Env:** `LYRA_LLM_MODEL=qwen2.5-14b-instruct`

`boot_oracle.bat` will try to start LM Studio automatically. If it's offline, everything else still works fine.

---

## Current State (Feb 2026)

```
tracks:            ~1,140
scored:            ~1,100 (10-dim emotional scores)
embeddings:        ~1,140 (CLAP vectors in ChromaDB)
acquisition_queue: ~1,100 pending (draining)
completed:         19,300+
library:           ~2,400 files on A: drive
```

---

## Project Layout

```
oracle/         — core Python package (CLI, acquirers, embedders, scorer, radio, etc.)
docker/         — Qobuz microservice (FastAPI)
desktop/        — Electron desktop app (in progress)
scripts/        — operational utilities
tests/          — test suite
data/           — Spotify exports, playlists
logs/           — runtime logs
staging/        — ingest staging area
.env.template   — copy to .env and fill in your values
boot_oracle.bat — double-click to start everything
oracle.bat      — CLI launcher (oracle <command>)
```

---

## Requirements

- Windows 10/11
- Python 3.12
- Node.js (for desktop app)
- Docker Desktop
- AMD or NVIDIA GPU (for CLAP embeddings — CPU fallback works but is slow)
- LM Studio (optional, for agent features)
- Qobuz account (for hi-fi tier)
- Real-Debrid account (for torrent tier)

---

*Built by a gamer who got tired of not owning his music.*
