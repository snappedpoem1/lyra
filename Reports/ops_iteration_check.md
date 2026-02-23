# Lyra Ops Iteration Report

- Generated: 2026-02-20T19:19:38
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
Validating 3 tracks (only unvalidated tracks)...

Validation workers: 32
[1/3]  Joey Bada$$              - Paper Trail$                        -> would fix (musicbrainz)
[2/3]  Flatbush Zombies         - Headstone                           -> would fix (musicbrainz)
[3/3] (Hed) P.E.                - Bartenders                          -> would fix (itunes)

=== Complete ===
Validated: 0
Fixed: 0
Would fix: 3
Failed: 0
Skipped (already complete): 0
```
- [OK] **drain**

```text
Skipped (drain_limit=0)
```
- [OK] **watch_once**

```text
Skipped (watch_once=False)
```
- [OK] **status**

```text
============================================================
LYRA ORACLE STATUS
============================================================
Write Mode: apply_allowed
Profile: performance | Paused: no

Database:
   Tracks (total): 864
   Tracks (active): 825
   Embeddings: 863
   Scored tracks: 736
   Vibes: 0
   Queue (pending): 1,675
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
