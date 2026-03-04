# Lyra Oracle - Current State

Last Updated: 2026-03-04 00:00:00 -05:00

## Project Direction

Lyra Oracle is evolving into a culturally-aware music recommendation system. The next phase goes beyond semantic search to integrate:

- **Cultural Insights**: Context-aware playlist curation that understands why a track fits a moment, not just that it does.
- **Spotify Data Integration**: Full use of `spotify_history` (637,860 rows) and `spotify_library` (4,015 rows) to personalize recommendations around the user's actual listening DNA.
- **Personalized Playlists**: Emotional arcs built from the 10-dimensional scoring model, shaped by the user's taste profile and real playback signals.
- **Semantic Search**: CLAP text-to-audio similarity as the discovery backbone — "angry driving rain", "late night focus", etc.

This is not a file manager with a search bar. It is a living instrument of music clairvoyance that serves the right track for the right moment.

---

## Runtime Health

- Doctor Result: WARNINGS (system functional)
- Python: 3.12 (OK)
- Database: writable (`C:\MusicOracle\lyra_registry.db`) (OK)
- Chroma Storage: present, 10 files (OK)
- Docker: daemon running (OK)
- Acquisition services: Prowlarr/rdtclient/slskd/spotdl all reachable (OK)
- Real-Debrid API: active (check expiry date)

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

## Active Priorities

1. **Spotify taste integration** — mine `spotify_history` + `spotify_library` to build user taste vectors and bootstrap personalized playlist scoring.
2. **Cultural context layer** — attach cultural/contextual metadata (era, origin, mood context) to tracks on ingest so recommendations can explain *why* a track fits.
3. **Playback layer** — `oracle serve` must be running continuously to build `playback_history`; Layer 5/6 (Radio + Playlust) depend on it.
4. **LLM classification** — wire async Ollama classification for ambiguous ingest cases; augment low-confidence CLAP scores.
5. **Queue drain** — 183 pending items; drain with `oracle drain --limit 50 --workers 3`.

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

