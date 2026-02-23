# Lyra Ops Iteration Report

- Generated: 2026-02-20T19:22:40
- Project: `C:\MusicOracle`

## Ordered Run
- [OK] **doctor**

```text
[OK] Python: Python 3.12
  [OK] FFmpeg: C:\Users\Admin\AppData\Local\Microsoft\WinGet\Links\ffmpeg.EXE
  [OK] fpcalc: C:\Users\Admin\AppData\Local\Microsoft\WinGet\Links\fpcalc.EXE
  [OK] Disk: C:\: 370.6 GB free
  [OK] Disk: A:\: 8734.0 GB free
  [OK] Database: Writable: C:\MusicOracle\lyra_registry.db
  [OK] ChromaDB (local): 10 files in chroma_storage
  [OK] Env: Core env keys present
  [OK] Docker: Daemon running
  [OK] Real-Debrid API: Active � 2050 pts, expires 2026-03-04
  [OK] Prowlarr (T1): Live at http://localhost:9696
  [OK] rdtclient (T1): Live at http://localhost:6500
  [OK] slskd (T2): Live at http://localhost:5030
  [OK] spotdl (T3): Available (Python package)
  [!!] LM Studio (LLM): Offline � LLM classification disabled

Doctor result: WARNINGS (system functional)
```
- [OK] **validate**

```text
Validating 1 tracks (only unvalidated tracks)...

Validation workers: 32
[1/1]  Flatbush Zombies         - Headstone                           -> would fix (musicbrainz)

=== Complete ===
Validated: 0
Fixed: 0
Would fix: 1
Failed: 0
Skipped (already complete): 0
```
- [OK] **drain**

```text
Draining 1 track(s) from queue (max tier: T4, workers: 32)...
  [OK] Senses Fail - Buried a Lie | T1 (qobuz) 6.4s

Done. 1 acquired, 0 failed.
Run 'oracle watch --once' to ingest any files in downloads/
[Waterfall] Senses Fail - Buried a Lie
  [T1] Trying Qobuz...
[Qobuz] Extracting app credentials from web bundle...
[Qobuz] Got app_id=798273057, 3 secrets
[Qobuz] Authenticating as snappedpoem@gmail.com...
[33mLogging...
[32mLogged: OK
[32mMembership: Studio
[Qobuz] Authenticated — subscription: Studio
[Qobuz] Matched: Senses Fail - Buried a Lie (score=1.00, id=131469798, hires=False)

[33mDownloading: Senses Fail - Buried a Lie (Live)

0.00/70.0k /// cover.jpg
70.0k/70.0k /// cover.jpg

0.00/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp
33.0k/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp
89.0k/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp
185k/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp 
399k/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp
718k/22.3M /// C:\MusicOracle\qobuz_9v1odkdc\Senses Fail - Joshua Tree\.01.tmp
1.16M/22.3M /// C:\Mus
```
- [OK] **watch_once**

```text
19:22:07 [INFO] [WATCHER] Watching: C:\MusicOracle\downloads, C:\MusicOracle\staging
19:22:07 [INFO] [WATCHER] Library dir: A:\music\Active Music
19:22:07 [INFO] [WATCHER] Waiting 10s for files to stabilize...
19:22:17 [INFO] [INGEST] Processing: Senses Fail - Buried a Lie.flac
19:22:18 [INFO] [INGEST] Moved: Senses Fail - Buried a Lie.flac
19:22:18 [INFO] [INGEST] Batch scan: {'scanned': 1, 'added': 1, 'updated': 0, 'quarantined': 0, 'errors': 0, 'track_ids': ['98c39720b452aa2b4fe545e037cb03e7']}
19:22:23 [INFO] Loading CLAP model: laion/larger_clap_music (attempt 1)
19:22:23 [INFO] HTTP Request: GET https://huggingface.co/api/models/laion/larger_clap_music/tree/main/additional_chat_templates?recursive=false&expand=false "HTTP/1.1 404 Not Found"
19:22:23 [INFO] HTTP Request: HEAD https://huggingface.co/laion/larger_clap_music/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
19:22:23 [WARNING] Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
19:22:
```
- [OK] **status**

```text
============================================================
LYRA ORACLE STATUS
============================================================
Write Mode: apply_allowed
Profile: performance | Paused: no

Database:
   Tracks (total): 865
   Tracks (active): 826
   Embeddings: 864
   Scored tracks: 737
   Vibes: 0
   Queue (pending): 1,674
   Spotify history: 637,860
   Spotify library: 4,015
   Playback events: 2

Acquisition Tiers:
   [OK] tier1_qobuz
   [OK] tier2_slskd
   [OK] tier3_realdebrid
   [OK] tier4_spotdl

Services:
   [OK] Docker: daemon running
   [OK] Prowlarr: HTTP 200
   [OK] rdtclient: HTTP 200
   [OK] slskd: HTTP 401 (live)
   [--] LM Studio: offline
============================================================
```
- [OK] **audit**

```text
#   ARTIST                    PLAYS    LIKED    LOCAL    STATUS
---------------------------------------------------------------------------
1   Coheed and Cambria        14905    LIKE 27  LOC 20   11% OWNED
2   Kendrick Lamar            11660    LIKE 31  LOC 1    1% OWNED
3   Brand New                 10740    LIKE 46  LOC 94   COMPLETE
4   Run The Jewels            9710     LIKE 12  LOC 3    3% OWNED
5   Drake                     9180     LIKE 31  LOC 1    1% OWNED
6   Childish Gambino          8450     LIKE 35  LOC 18   23% OWNED
7   Kanye West                7855     LIKE 21  LOC 1    1% OWNED
8   J. Cole                   7435     LIKE 26  LOC 2    2% OWNED
9   JID                       6330     LIKE 11  LOC 4    9% OWNED
10  Thrice                    5920     LIKE 22  LOC 16   30% OWNED
11  Tyler, The Creator        5900     LIKE 11  LOC 112  COMPLETE
12  Aesop Rock                5795     LIKE 23  LOC 15   18% OWNED
13  Muse                      5210     LIKE 20  LOC 0    UNOWNED
14  Arctic Monkeys            5200     LIKE 23  LOC 0    UNOWNED
15  Logic                     5055     LIKE 18  LOC 2    2% OWNED
16  Bayside                   4940     LIKE 7   LOC 6    17% OWNED
1
```

## Environment Scope

```json
{
  "python": "3.12.0",
  "cwd": "C:\\MusicOracle",
  "tools": {
    "docker": true,
    "ffmpeg": true,
    "fpcalc": true
  },
  "env_present": {
    "PROWLARR_URL": true,
    "PROWLARR_API_KEY": true,
    "REAL_DEBRID_KEY": true,
    "REAL_DEBRID_API_KEY": false,
    "SLSKD_API_KEY": false,
    "LYRA_LLM_BASE_URL": true,
    "LYRA_LLM_MODEL": true,
    "LYRA_LM_STUDIO_EXE": false,
    "LYRA_ALLOW_GUARD_BYPASS": false,
    "LYRA_DB_PATH": false,
    "LIBRARY_BASE": true,
    "DOWNLOADS_FOLDER": true,
    "STAGING_FOLDER": false
  },
  "missing_required": []
}
```

## Missing Pieces
- LM Studio is offline; LLM-enhanced paths remain disabled.
