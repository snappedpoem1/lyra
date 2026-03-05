# Worklist

Last updated: March 5, 2026 (updated after codebase-integrity-pass session)

This file is the short operational list of what is done and what still needs work.

## Completed in this cycle

- [x] **Codebase integrity pass** — multi-milestone audit + fix session:
  - M0: Fixed `AcquisitionWaterfall` `ImportError` crash in `worker.py` (acquisition drain was broken for every run)
  - M0: Fixed `guard._check_duplicate()` hardcoded relative `sqlite3.connect()` path
  - M0: Fixed T3 slskd returning `success=True` on queued (not-yet-downloaded) status
  - M1: Wrapped 10+ connection-leaking call sites in `try/finally` across `radio.py`, `vibes.py`, `ingest_watcher.py`, `waterfall.py`, `acquire.py` blueprint
  - M1: Converted `radio._store_queue()` DELETE+INSERT to atomic transaction with `ROLLBACK`
  - M1: Added `executemany` batch INSERT to `radio._store_queue()` and `normalizer.py`
  - M1: Added `_BATCH_JOB_TTL` eviction to `acquire.py` batch jobs dict
  - M1: Added `SmartAcquisition.__enter__`/`__exit__` context-manager support
  - M2: Removed hardcoded `DOWNLOAD_DIR`/`STAGING_DIR` constants from `realdebrid.py`, `spotdl.py`, `ytdlp.py` — all now read from `oracle.config`
  - M2: Fixed `add_torrent_file()` in `realdebrid.py` to use retry-wrapped `_request()` instead of raw `requests.put()`
  - M2: Removed dead `check_instant_availability()` HTTP call in `realdebrid.acquire_from_magnet()`
  - M2: Replaced `asyncio.run()` in waterfall T3 with a safe wrapper that detects running event loop
  - M2: Converted `qobuz.py` module-level `os.getenv()` globals to `_get_qobuz_config()` lazy function
  - M2: Created `oracle/acquirers/streamrip.py` stub so T2 waterfall import no longer raises `ImportError`
  - M2: Changed APScheduler `max_workers` from 2 → 5
  - M3: Refactored `scorer.score_all()` to batch-fetch all embeddings in one ChromaDB call and persist via `executemany` (eliminates N per-track Chroma calls)
  - M3: Replaced `radio.get_chaos_track()` O(n) Python cosine loop with ChromaDB ANN query using negated vector
  - M3: Replaced per-row `cursor.execute()` loop in `normalizer.py` with `cursor.executemany()`
- [x] Harden CLAP audio loading resilience for ingest/scoring:
  - Added `soundfile` fallback path when `librosa.load()` fails (`ZeroDivisionError`/backend decode failures seen in pipeline logs)
  - Added safe normalization guard for silent/invalid waveforms
  - Added regression tests in `tests/test_clap_embedder_audio_loading.py`
- [x] Repair `scripts/new_session.ps1` parse break (mojibake corruption) so session bootstrap works again
- [x] Add import dedup guard for future Spotify history loads
- [x] Generate a clean, priority-scored acquisition queue from real Spotify history
- [x] Create `oracle/taste_backfill.py` to bridge Spotify history into `taste_profile`
- [x] Seed Lyra taste from real listening history for matched local tracks
- [x] Add CLI + API path for taste backfill
- [x] Fix broken `/api/acquire/batch` call path
- [x] Remove per-item batch dead sleep in `smart_pipeline`
- [x] Reduce startup / polling waits that added avoidable latency
- [x] Archive unused `oracle/downloader.py`
- [x] Wire desktop playback reporting into the backend feedback loop
- [x] Agent action router (`agentActionRouter.ts`), context menus, queue drag-to-reorder, transport waveform, playlist mosaic, keyboard shortcuts, playback position persistence
- [x] Harden Last.fm similarity-edge builder for pylast response variants
- [x] Add batch controls for similarity runs (`oracle graph similarity-edges --limit-artists --top-k`)
- [x] Add controlled worker concurrency + chunked DB commits for similarity runs (`--workers`, `--request-pause`, `--commit-every`)
- [x] Populate local-library similar edges from Last.fm in staged runs (`similar` edges: 0 -> 1,762)
- [x] Run incremental MusicBrainz credit enrichment (`track_credits`: 1 -> 7)
- [x] Verify structure analysis blocker (`librosa_not_installed` in current runtime)

## Next up

- [ ] Improve Spotify-history-to-local-track matching quality
- [ ] Add stronger normalization / fuzzy fallback for near-miss artist-title matches
- [ ] Audit any remaining acquisition/API bypasses against canonical queue + waterfall paths
- [ ] Verify desktop playback reporting behavior across skip / finish / manual track-switch cases
- [ ] Re-evaluate embedded player direction from the now-live taste foundation
- [ ] Expand playback telemetry only where it improves recommendation quality

## Progress markers (easy -> hard)

- [ ] P1: Install `librosa` in the active Python runtime; rerun `oracle structure analyze --limit 50` and confirm `track_structure` growth.
- [ ] P2: Continue `oracle credits enrich` in bounded batches (20-50/run) until artist shrine credit coverage becomes useful.
- [ ] P3: Continue staged `oracle graph similarity-edges` runs (`limit-artists=500` then full) to deepen cultural graph edges.
- [ ] P4: Investigate why `oracle discover listenbrainz` returns `0` queued tracks; verify API payloads, duplicate filtering, and queue insert guards.
- [ ] P5: Improve Spotify-history to local-track resolution with stronger normalization/fuzzy matching, then re-run playlist parity audit.
- [ ] P6: Run an explicit live foobar2000 + BeefWeb verification session and confirm new playback rows are clearly attributable to live playback.
- [ ] P7: Decide on Spotify export implementation scope (or explicit cancellation) and runtime-artifact separation policy.

## To Done

- Documentation stack rewritten around audited repo reality.
- Historical exports, prototype notes, and old workspace material distilled into reference docs.
- README replaced with a cleaner current-project description.
- `.claude` memory and agent reference files synchronized to one source-of-truth order.
- Legacy roadmap and planning files marked as historical.
- VS Code workspace auto-start added for Docker-backed services on folder open.
- Dead `prowlarr` and `lidarr` image pins removed from `docker-compose.yml`.
- Desktop text search rewired to `/api/search` instead of vibe generation.
- Desktop command palette rewired to `/api/agent/query` instead of a hardcoded stub.
- Constellation fixture masking removed for normal runtime; fixture fallback now only happens in explicit fixture mode.
- Home, Oracle, and playlist detail routes now surface constellation backend failures instead of hiding them.
- Flask runtime now attempts to auto-start the BeefWeb playback bridge when the API starts and BeefWeb is reachable.

## To Do

- Verify real playback ingestion with foobar2000 + BeefWeb and confirm `playback_history` starts filling.
- Decide whether command-palette agent responses should trigger app-side actions, not just display backend intent.
- Deepen graph edge types so constellation and discovery have richer cultural context.
- Clean up duplicate or legacy containers such as `lyra_node` and `lyra_transport`.
- Decide whether runtime artifacts should remain in-repo or move to a dedicated runtime root.

## Blocked Or External

- Playback ingestion cannot be proven complete without a live foobar2000 + BeefWeb session.
- Some acquisition/runtime validation still depends on whichever Docker services and credentials are active on the machine at the time.
