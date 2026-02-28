# Lyra

Lyra is a local-first music library and desktop player built around playlists and listening threads.

## Features

- Local library indexing and playback
- Flask API for health, library, search, radio, dossier, and streaming
- Electron desktop app built with Vite, React, and TypeScript
- Queue management, dossier inspection, and listening-thread workflows
- LLM/provider diagnostics for AI-dependent features

## Requirements

- Windows 10 or 11
- Python 3.12+
- Node.js 20+
- SQLite
- Docker Desktop for optional service dependencies

Optional:
- LM Studio or another configured LLM provider
- Qobuz / Real-Debrid / related acquisition credentials

## Repository Layout

```text
oracle/                  Core Python package
  acquirers/             Acquisition pipeline and guard logic
  db/                    SQLite schema and migrations
  embedders/             Embedding/indexing support
  enrichers/             Metadata enrichment providers
desktop/                 Electron desktop shell
  renderer-app/          React + Vite renderer
docker/                  Service images
scripts/                 Diagnostics and helper scripts
tests/                   Python tests
lyra_api.py              Flask API server
requirements.txt         Python dependencies
.env.template            Environment template
```

## Setup

```powershell
cd C:\MusicOracle
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.template .env
```

Fill in the values you actually use in `.env`.

## Environment

### Backend

```powershell
LYRA_API_TOKEN=
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,null
LYRA_LLM_PROVIDER=local
LYRA_LLM_BASE_URL=http://127.0.0.1:1234/v1
LYRA_LLM_MODEL=qwen2.5-14b-instruct
LYRA_LLM_FALLBACK_MODEL=
LYRA_LLM_API_KEY=
```

Supported LLM provider values:
- `local`
- `openai`
- `openai_compatible`
- `anthropic`
- `disabled`

### Desktop

```powershell
VITE_LYRA_API_BASE=http://localhost:5000
VITE_LYRA_API_TOKEN=
```

## Run

### Backend

```powershell
cd C:\MusicOracle
.venv\Scripts\python.exe lyra_api.py
```

Or:

```powershell
oracle serve
```

### Desktop

```powershell
cd C:\MusicOracle
powershell -ExecutionPolicy Bypass -File .\scripts\dev_desktop.ps1
```

Manual workflow:

```powershell
cd C:\MusicOracle\desktop
npm install
npm run dev
```

## Desktop

Connectivity states:
- `LIVE`: backend reachable and serving real data
- `DEGRADED`: backend unreachable or returning errors
- `FIXTURE`: explicit offline fixture mode enabled in Settings

Primary workflow:
1. open the player workspace
2. browse the library or a saved listening thread
3. play a real local track
4. inspect queue and dossier state while listening
5. pivot with Oracle/Auto-DJ without losing the current thread

## Diagnostics

Check LLM/provider configuration:

```powershell
cd C:\MusicOracle
powershell -ExecutionPolicy Bypass -File .\scripts\check_llm_config.ps1
```

Run desktop/backend smoke checks:

```powershell
cd C:\MusicOracle
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_desktop.ps1
```

## Tests

```powershell
cd C:\MusicOracle
.venv\Scripts\python.exe -m pytest tests\test_llm_config.py tests\test_lyra_api_contract.py
```

Renderer build:

```powershell
cd C:\MusicOracle
npm --prefix desktop\renderer-app run build
```

## API

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
