# Lyra Oracle

AI-powered music intelligence system built on a Windows gaming rig.

Turn a Spotify listening history into a locally owned, semantically searchable, emotionally intelligent music archive. No subscriptions. No cloud. No bullshit.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Electron](https://img.shields.io/badge/desktop-electron-47848F.svg)](https://www.electronjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

- Acquires music with a 4-tier waterfall: Qobuz hi-fi FLAC -> Soulseek P2P -> Real-Debrid -> SpotDL fallback
- Understands music with CLAP embeddings and semantic search
- Scores every track on a 10-dimensional emotional model
- Learns your taste from playback signals
- Builds dynamic vibes and playlist-like curation objects
- Runs smart radio modes for chaos, flow, and discovery
- Ships a desktop app in `desktop/` with a React/Vite renderer, playlist detail, search, oracle surfaces, right-rail playback, a visualizer, and Windows installer flow

---

## Hardware This Runs On

```text
CPU: AMD Ryzen 7 7800X3D
GPU: AMD Radeon RX 9070 XT (16GB)
RAM: 32GB
Storage: 8TB A: drive (music library)
OS: Windows 11
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
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
oracle db migrate
oracle import spotify --data-dir data/
oracle drain --limit 100 --workers 3 --max-tier 5
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
Layer 0: Infrastructure - Docker, Qobuz, Slskd, Prowlarr, LM Studio
Layer 1: Data           - SQLite registry plus imported history
Layer 2: Embeddings     - CLAP vectors in ChromaDB
Layer 3: Scores         - 10-dimensional emotional scoring
Layer 4: Acquisition    - Guarded staging to verified to active pipeline
Layer 5: Playback       - Taste learning from play and skip signals
Layer 6: Intelligence   - Radio, vibes, semantic search, oracle flows
Layer 7: Desktop        - Electron shell and React renderer
```

Fix the lowest broken layer first.

---

## Core CLI Commands

```bash
# System
oracle status
oracle doctor
oracle serve

# Library
oracle scan --library "A:\music\Active Music"
oracle index --library "A:\music\Active Music"
oracle score --all

# Search and Radio
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
oracle played --artist X --title Y
oracle played --artist X --title Y --skipped
```

---

## The 10 Dimensions

Every track is scored on:

```text
energy
valence
tension
density
warmth
movement
space
rawness
complexity
nostalgia
```

These power semantic search, radio, playlist storytelling, and the desktop experience.

---

## Project Layout

```text
oracle/                core Python package
docker/                Qobuz microservice
desktop/               Electron shell and Windows installer packaging
desktop/renderer-app/  React + Vite renderer used by the Electron shell
scripts/               operational utilities
tests/                 test suite
data/                  Spotify exports and playlists
logs/                  runtime logs
staging/               ingest staging area
.env.example           copy to .env and fill in your values
boot_oracle.bat        start services and optional local LLM
oracle.bat             CLI launcher
```

---

## Requirements

- Windows 10 or 11
- Python 3.12
- Node.js
- Docker Desktop
- AMD or NVIDIA GPU preferred for CLAP embeddings
- LM Studio optional for agent features
- Qobuz account for hi-fi acquisition
- Real-Debrid account for torrent acquisition

---

Built by a gamer who got tired of not owning his music.
