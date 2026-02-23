# Lyra Oracle - Current State

Last Updated: 2026-02-21 17:53:36 -05:00

## Runtime Health

- Doctor Result: WARNINGS (system functional)
- Python: 3.12 (OK)
- Database: writable (`C:\MusicOracle\lyra_registry.db`) (OK)
- Chroma Storage: present, 10 files (OK)
- Docker: daemon running (OK)
- Acquisition services: Prowlarr/rdtclient/slskd/spotdl all reachable (OK)
- Real-Debrid API: active, expires 2026-03-04 (OK)

## LM Studio Status

- Daemon: running (`v0.4.4+1`)
- Server: running on `127.0.0.1:1234`
- Loaded model: `qwen2.5-coder-14b-instruct-abliterated`
- Configured model (`LYRA_LLM_MODEL`): `qwen2.5-14b-instruct`
- Current warning: configured model is not the loaded model

## Library / DB Snapshot

From `python -m oracle.cli status`:

- Tracks (total): 2,331
- Tracks (active): 2,292
- Embeddings: 2,330
- Scored tracks: 2,330
- Queue (pending): 183
- Spotify history rows: 637,860
- Spotify library rows: 4,015

## Immediate Action Needed

To clear LM warning, do one of these:

1. Load configured model:
   `lms load qwen2.5-14b-instruct`
2. Or update `.env` `LYRA_LLM_MODEL` to the model you actually run:
   `qwen2.5-coder-14b-instruct-abliterated`

## Notes

- LM Studio path resolution is pinned to your install path in `.env` via `LYRA_LM_STUDIO_EXE`.
- CLI path is pinned via `LYRA_LMS_CLI_EXE` to avoid old/stale location fallback.

## App Runtime Differences

When `python -m oracle.cli serve` is running, this is what differs from static CLI checks:

- `/health` responds slowly (~8.7s) and reports LLM unavailable:
  - `llm.status=unavailable`
  - `llm.error=\"Request timed out.\"`
- `/api/status` responds fast (~0.03s) and matches DB snapshot values:
  - `tracks=2331`
  - `embeddings=2330`
  - `queue_pending=183`
  - `vibes=0`
- Practical impact:
  - Core API is up.
  - LLM-backed app features may be degraded even though LM Studio itself is running.
