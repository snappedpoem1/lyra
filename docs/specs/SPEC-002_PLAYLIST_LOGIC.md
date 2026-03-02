# SPEC-002: Playlist Generation & Persistence Logic

## 1. Objective
Update `oracle/vibes.py` to save every generated playlist into the new database tables defined in SPEC-001.
The system must no longer just 'return a list of tracks'. It must return a persisted `PlaylistRun` object.

## 2. Required Changes in `oracle/vibes.py`

### 2.1 Imports
Must import:
- `json`, `uuid`, `sqlite3`, `datetime`
- `DB_PATH` from `oracle.db.schema`
- `PlaylistRun`, `PlaylistTrack`, `TrackReason` from `oracle.types`

### 2.2 Function: `save_playlist_run(run: PlaylistRun)`
Create a helper function that:
1. Connects to SQLite.
2. Inserts the `PlaylistRun` data into `playlist_runs`.
3. Iterates through `run.tracks` and inserts each into `playlist_tracks`.
   - **CRITICAL:** The `reasons` field must be serialized to a JSON string (`json.dumps`) before insertion.
4. Commits and closes.

### 2.3 Update: `generate_vibe(...)` (or equivalent)
Modify the main generation function to:
1. Perform the existing vector search.
2. Construct a `PlaylistRun` object:
   - `uuid`: Generate a new UUID4.
   - `prompt`: The user's input.
   - `created_at`: Current UTC time.
3. Convert search results into `PlaylistTrack` objects:
   - Map `score` from search to `global_score`.
   - Create a default `TrackReason` (type='semantic_search', text='Matched vibe prompt', score=row_score).
4. Call `save_playlist_run(run)`.
5. Return the `PlaylistRun` object (Pydantic model) instead of a raw list/dict.

## 3. Backward Compatibility
If existing CLI tools expect a raw list of paths, update the CLI entry point (`oracle/cli.py` or `__main__.py`) to extract `.tracks` from the returned `PlaylistRun` object so they don't break.