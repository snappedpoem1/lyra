# Lyra Oracle

AI-powered music intelligence system built on a Windows gaming rig.

Turn a Spotify listening history into a locally owned, semantically searchable, emotionally intelligent music archive. No subscriptions. No cloud. No bullshit.

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)
[![Electron](https://img.shields.io/badge/desktop-electron-47848F.svg)](https://www.electronjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

- Acquires music with a 4-tier waterfall: Qobuz hi-fi FLAC → Soulseek P2P → Real-Debrid → SpotDL fallback
- Understands music with CLAP embeddings and semantic search
- Scores every track on a 10-dimensional emotional model
- Learns your taste from playback signals
- Builds dynamic vibes and playlist-like curation objects
- Runs smart radio modes for chaos, flow, and discovery
- Ships a desktop app with a React/Vite renderer, playlist detail, search, oracle surfaces, right-rail playback, and a real-time visualizer

---

## Hardware This Runs On

```text
CPU:     AMD Ryzen 7 7800X3D
GPU:     AMD Radeon RX 9070 XT (16 GB VRAM, RDNA 4)
RAM:     32 GB
Storage: 8 TB A: drive (music library)
OS:      Windows 11 Pro
```

It will probably run on other setups, but this is what it was built and tested on.

---

## Quick Start

Double-click `boot_oracle.bat`. It starts Docker Desktop if needed, brings up all services, and can optionally load the LM Studio model.

Then in any terminal:

```bash
oracle status
oracle doctor
oracle serve
```

### First-Time Setup

```bash
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.template .env          # fill in your API keys
oracle db migrate
oracle scan --library "A:\music\Active Music"
oracle index --library "A:\music\Active Music"
oracle score --all
oracle drain --limit 100 --workers 3 --max-tier 4
```

---

## Desktop App

The Electron shell lives in `desktop/`. The renderer lives in `desktop/renderer-app/`.

### Desktop Development

Start the Python API first:

```bash
oracle serve
```

Then start the desktop app:

```bash
cd desktop
npm install
npm run dev
```

### Renderer-Only Build Check

```bash
cd desktop\renderer-app
npm install
npm run build
```

### Build the Windows Installer

```bash
cd desktop
npm run build
```

### Install or Update From the Newest Built Installer

```bash
cd desktop
npm run installer:update
```

Build first, then install or update:

```bash
cd desktop
npm run installer:update:build
```

The updater script re-runs the newest `Lyra Oracle Setup *.exe` from `desktop\dist`.

---

## Architecture

```text
Layer 0  Infrastructure   Docker, Qobuz, Slskd, Prowlarr, LM Studio
Layer 1  Data             SQLite registry + imported Spotify history
Layer 2  Embeddings       CLAP vectors in ChromaDB (AMD GPU via ROCm)
Layer 3  Scores           10-dimensional emotional scoring
Layer 4  Acquisition      4-tier waterfall → guard → staging → library
Layer 5  Playback         foobar2000 + BeefWeb → taste learning
Layer 6  Intelligence     Radio, vibes, semantic search, oracle flows
Layer 7  Desktop          Electron shell + React/Vite renderer
```

Fix the lowest broken layer first.

---

## Core CLI Commands

```bash
# System
oracle status                                      # Row counts + system state
oracle doctor                                      # Full diagnostics
oracle serve                                       # Start Flask API server

# Library
oracle scan --library "A:\music\Active Music"      # Scan audio files
oracle index --library "A:\music\Active Music"     # Generate CLAP embeddings
oracle score --all                                 # Score all tracks on 10 dimensions
oracle pipeline --library "A:\music\Active Music"  # Scan + index + score in one pass

# Search
oracle search --query "dark ambient" --n 20        # Semantic search via CLAP
oracle search --query "warm vinyl jazz" --nl       # Natural language mode (LLM rewrite)

# Acquisition
oracle drain --limit 100 --workers 3 --max-tier 4  # Drain queue via 4-tier waterfall
oracle acquire waterfall --artist "Burial" --title "Archangel"
oracle catalog acquire --artist "Massive Attack"   # Full discography via MusicBrainz
oracle import --source staging                     # Beets auto-tag + organize + ingest

# Vibes
oracle vibe save --name "Late Night" --query "dark minimal electronic"
oracle vibe materialize --name "Late Night" --mode hardlink
oracle vibe list

# Taste Learning
oracle played --artist "Burial" --title "Archangel"            # Positive signal
oracle played --artist "Burial" --title "Archangel" --skipped  # Negative signal

# Curation
oracle curate classify                             # Classify track quality
oracle guard test --artist "Burial" --title "Archangel"
oracle normalize --apply                           # Normalize metadata
```

---

## The 10 Dimensions

Every track is scored 0 → 1 on each dimension using CLAP anchor embeddings:

```text
energy      ambient / still ←→ explosive / driving
valence     sad / hopeless ←→ ecstatic / euphoric
tension     relaxed / resolved ←→ horror / panic / dissonant
density     solo / bare ←→ massive / wall-of-sound
warmth      cold / robotic ←→ warm / analog / soulful
movement    frozen / drone ←→ driving / groove / danceable
space       intimate / dry ←→ vast / cathedral / oceanic
rawness     polished / pristine ←→ distorted / lo-fi / garage
complexity  simple / repetitive ←→ progressive / virtuosic
nostalgia   modern / futuristic ←→ retro / vintage / throwback
```

These power semantic search, radio, playlist sequencing, and the desktop experience.

---

## Docker Services

```bash
docker-compose up -d    # Start all services
docker-compose ps       # Check status
oracle doctor           # Verify health
```

| Service   | Container        | Port  | Purpose                        |
|-----------|------------------|-------|--------------------------------|
| Qobuz     | `lyra_qobuz`     | 7700  | Hi-fi FLAC acquisition (T1)    |
| Slskd     | `lyra_slskd`     | 5030  | Soulseek P2P client (T2)       |
| Prowlarr  | `lyra_prowlarr`  | 9696  | Torrent indexer for RD (T3)    |
| rdtclient | `lyra_rdtclient` | 6500  | Real-Debrid download manager   |

---

## Project Layout

```text
oracle/                  Core Python package (CLI, acquirers, embedders, scorer, search, radio)
  acquirers/             4-tier waterfall + guard + validator
  embedders/             CLAP embedder (laion/larger_clap_music)
  enrichers/             MusicBrainz, Last.fm, Genius, Discogs
  integrations/          Beets import, BeefWeb listener
  db/                    SQLite schema + migrations
desktop/                 Electron shell + Windows installer
  renderer-app/          React + Vite + TanStack Router + Zustand
docker/                  Qobuz microservice (Dockerfile + FastAPI)
scripts/                 Operational utilities
tests/                   Test suite (14 tests)
data/                    Spotify exports
logs/                    Runtime logs
staging/                 Ingest staging area
.env.template            Copy to .env and fill in your keys
boot_oracle.bat          Start Docker + services + optional LLM
oracle.bat               CLI launcher
lyra.bat                 CLI launcher (alias)
```

---

## Requirements

- Windows 10 or 11
- Python 3.14
- Node.js 24+
- Docker Desktop
- AMD GPU with ROCm (tested) or NVIDIA GPU with CUDA for CLAP embeddings
- LM Studio with qwen2.5-14b-instruct for agent features (optional)
- Qobuz account for hi-fi acquisition (T1)
- Real-Debrid account for torrent acquisition (T3)

---

Built by a gamer who got tired of not owning his music.
