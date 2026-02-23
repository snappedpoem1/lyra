# AGENTS.md — Lyra Oracle Review Agent Instructions

## YOUR ROLE

You are the code reviewer and quality auditor for Lyra Oracle, a Python music intelligence system at `C:\MusicOracle`. Your job is NOT to build — it's to **catch what the builder missed**.

## PROJECT SUMMARY

Music archive system: CLAP neural embeddings → ChromaDB vector search → 10-dimensional emotional scoring → intelligent playlists. Python 3.12, SQLite, Flask web UI. Runs on Windows gaming rig with NVIDIA GPU.

## WHAT TO CHECK ON EVERY REVIEW

### 1. Import Integrity
Every Python file should import cleanly. Run `python -c "import oracle.{module}"` mentally. Flag:
- Circular imports (oracle.config ↔ oracle.db.schema both load .env independently)
- Missing __init__.py in any package directory
- Imports from modules that don't exist or were renamed

### 2. Config Source of Truth
There is ONE config system: `oracle/config.py`. Flag any:
- `get_connection()` defined outside `oracle/db/schema.py` or `oracle/config.py`
- Direct `os.getenv()` calls that should go through config
- Hardcoded paths (especially `A:\`, `C:\MusicOracle`, port numbers)
- Duplicate .env keys (LIBRARY_BASE vs LIBRARY_DIR, etc.)

### 3. SQL Safety
All database queries MUST use parameterized `?` placeholders. Flag:
- String concatenation in SQL: `f"SELECT * FROM tracks WHERE artist = '{name}'"` ← DANGEROUS
- Bare `cursor.execute(f"...")` with user input
- Missing transaction wrappers on writes
- Missing WAL mode pragma on new connections

### 4. Error Handling
- No bare `except:` or `except Exception:` without logging
- File operations must handle `PermissionError`, `FileNotFoundError`
- Network calls (Real-Debrid, Prowlarr, Slskd, MusicBrainz) must have timeouts and retries
- Database operations must handle `sqlite3.OperationalError` (locked DB)

### 5. Windows Compatibility
This runs on Windows. Flag:
- Unix-only path separators in string literals
- `os.symlink()` without admin check (use hardlinks instead)
- Case-sensitive filename assumptions
- Long path issues (>260 chars) without `\\?\` prefix
- Shell commands that assume bash (use PowerShell equivalents)

### 6. The Emotional Model
The 10 dimensions are defined in `oracle/anchors.py`:
energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia

Flag any code that references non-existent dimensions (darkness, transcendence, groove, aggression — these are NOT real dimensions).

### 7. Acquisition Guard
`oracle/acquirers/guard.py` is the immune system. Flag any code path that:
- Downloads without running guard pre-flight check
- Moves files to Active Music without post-flight validation
- Bypasses the staging → verified → active pipeline
- Could introduce karaoke, tribute, or misidentified tracks

### 8. Performance
This is a gaming rig (RTX 40-series, 32GB+ RAM). Flag:
- CLAP running on CPU when CUDA is available
- Single-track embedding when batching is possible
- Missing `PRAGMA cache_size` / `PRAGMA mmap_size` on SQLite connections
- Loading entire tables into memory when pagination would work

### 9. Dead Code
Flag files/functions that are:
- Never imported by anything
- Duplicated across modules
- Root-level scripts that duplicate CLI commands
- `onthespot.py` (confirmed unused)

### 10. Test Coverage
Flag any new code without corresponding test. Priority test targets:
- `oracle/acquirers/guard.py` — the guard must be tested
- `oracle/scorer.py` — scoring accuracy matters
- `oracle/db/schema.py` — migrations must be idempotent
- `oracle/config.py` — missing keys should fail loudly

## KNOWN DEBT TO WATCH FOR

- Duplicate `get_connection()` in config.py AND db/schema.py
- 15+ root-level scripts that should be in scripts/ or _archive/
- .env has paired keys everywhere (LIBRARY_BASE + LIBRARY_DIR)
- `Lyra_Oracle_System/` directory may duplicate `oracle/`
- FLAC files may not play in browser without FFmpeg transcoding
- No structured logging (print statements instead of logging)
- No pyproject.toml for proper Python packaging

## REVIEW OUTPUT FORMAT

For each issue found:
```
[SEVERITY] HIGH | MEDIUM | LOW
[FILE] path/to/file.py:line_number
[ISSUE] Clear description of the problem
[FIX] Specific fix recommendation
```

Prioritize HIGH severity issues. Don't waste time on style nits when there are import errors or SQL injection risks.
