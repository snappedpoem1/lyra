# Top-10 Discography Execution Report (2026-02-24)

## Objective
Run top-10 artist discography acquisition to completion, fix blockers, and verify end-to-end audio track processing.

## Commands Executed
- `python scripts/lyra_acquire.py --top-discographies --top-n 10 --quality FLAC`
- `python -c "from oracle.scanner import scan_library; ..."`
- `python -c "from oracle.scorer import score_all; ..."`

## Blockers Found and Fixed
1. **Repeated Tier-1 stalls when Prowlarr offline**
- Symptom: per-track Prowlarr retries with connection-refused spam and long runtime.
- Fix: added Prowlarr cooldown fast-fail in `oracle/hunter.py`.

2. **Spotify API rate-limit hangs (429 retry windows ~22h)**
- Symptom: top-discography fetch stalled on huge retry-after.
- Fixes in `scripts/lyra_acquire.py`:
  - fail-fast Spotify call wrapper for excessive retry windows,
  - disabled Spotipy internal retries (`retries=0`, `status_retries=0`),
  - fallback to local `spotify_history` when Spotify catalog calls fail.

3. **Concurrent duplicate acquisition runs**
- Symptom: duplicate `lyra_acquire` processes running at once.
- Fix: single-run lock added in `scripts/lyra_acquire.py`.

## Top-10 Run Result
- Final run summary in log:
  - `artists_total: 10`
  - `artists_completed: 10`
  - `artists_failed: 0`
- Harvest summary snapshot:
  - `{'complete': 47, 'failed': 0, 'skipped': 0, 'dry_run': 0}`

## Post-Acquisition Pipeline Completion
- Library scan completed:
  - `{'scanned': 3901, 'added': 1961, 'updated': 1940, 'quarantined': 0, 'errors': 0}`
- Embedding coverage after indexing: `missing_embedding_active = 0`
- Scoring completed for previously unscored tracks:
  - `score_all -> {'scored': 452, 'persisted': 452, 'errors': 0}`
- Final DB state:
  - `tracks_active = 2751`
  - `track_scores_rows = 2785`
  - `missing_scores_active = 0`

## End-to-End Track Verification (Sample)
- Track: `Kanye West - The New Workout Plan`
- File exists: `A:\music\Active Music\The New Workout Plan - Kanye West.flac`
- `tracks` row: present + `status='active'`
- `embeddings` row: present (`model='clap_htsat_unfused'`)
- `track_scores` row: present (all 10 dimensions + `score_version=2`)

## Artifacts
- `Reports/top10_discography_run_20260224_final.log`
- `Reports/top10_discography_execution_20260224.md`
