"""Vibe system for Lyra Oracle - semantic playlist management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from oracle.config import VIBES_FOLDER
from oracle.db.schema import DB_PATH, get_connection, get_write_mode
from oracle.search import search
from oracle.types import PlaylistRun, PlaylistTrack, TrackReason

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIBES_DIR = VIBES_FOLDER


def _reason_to_dict(reason: TrackReason) -> Dict[str, Any]:
    if hasattr(reason, "model_dump"):
        return reason.model_dump()
    return reason.dict()


def save_playlist_run(
    run: PlaylistRun,
    *,
    params: Optional[Dict[str, Any]] = None,
    vibe_name: Optional[str] = None,
) -> int:
    """Persist a playlist run and its tracks."""
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO playlist_runs (uuid, prompt, params, created_at, is_saved_vibe, vibe_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run.uuid,
                run.prompt,
                json.dumps(params or {}),
                run.created_at.isoformat(),
                1 if vibe_name else 0,
                vibe_name,
            ),
        )
        run_id = int(cursor.lastrowid)

        track_values = []
        for track in run.tracks:
            reasons_json = json.dumps([_reason_to_dict(reason) for reason in track.reasons])
            track_values.append(
                (
                    run_id,
                    track.path,
                    track.rank,
                    track.global_score,
                    reasons_json,
                )
            )

        if track_values:
            cursor.executemany(
                """
                INSERT INTO playlist_tracks (run_id, track_path, rank, score, reasons)
                VALUES (?, ?, ?, ?, ?)
                """,
                track_values,
            )

        conn.commit()
        return run_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_vibe(prompt: str, n: int = 20, vibe_name: Optional[str] = None) -> PlaylistRun:
    """Generate a playlist run from semantic search and persist it when writes are enabled."""
    results = search(prompt, n=n)

    playlist_tracks: List[PlaylistTrack] = []
    for index, result in enumerate(results, start=1):
        raw_score = result.get("score", 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0

        playlist_tracks.append(
            PlaylistTrack(
                path=result.get("path") or result.get("filepath") or "",
                artist=result.get("artist") or "Unknown",
                title=result.get("title") or "Unknown",
                rank=index,
                global_score=score,
                reasons=[
                    TrackReason(
                        type="semantic_search",
                        score=score,
                        text="Matched vibe prompt",
                    )
                ],
            )
        )

    run = PlaylistRun(
        uuid=str(uuid.uuid4()),
        prompt=prompt,
        created_at=datetime.now(timezone.utc),
        tracks=playlist_tracks,
    )

    # Enrich playlist with structured reasons (F-007) — silent on failure
    try:
        from oracle.explain import ReasonBuilder
        rb = ReasonBuilder()
        rb.enrich_playlist(run.tracks, query=prompt, include_mood_bridge=True)
    except Exception as _exc:
        logger.debug("ReasonBuilder enrichment skipped: %s", _exc)

    if get_write_mode() == "apply_allowed":
        save_playlist_run(run, params={"query": prompt, "n": n}, vibe_name=vibe_name)
    else:
        print("Warning: LYRA_WRITE_MODE is not apply_allowed; PlaylistRun not saved to DB.")

    return run


def save_vibe(name: str, query: str, n: int = 200) -> Dict[str, Any]:
    """
    Save a vibe profile by running a semantic search and storing results.
    
    Args:
        name: Vibe name (must be unique, filesystem-safe)
        query: Semantic search query
        n: Number of tracks to include
        
    Returns:
        Dict with status and track count
    """
    if get_write_mode() != "apply_allowed":
        return {'error': 'LYRA_WRITE_MODE must be apply_allowed to save vibes'}
    
    # Sanitize name for filesystem
    safe_name = name.strip()
    if not safe_name:
        return {'error': 'Vibe name cannot be empty'}
    
    try:
        run = generate_vibe(prompt=query, n=n, vibe_name=safe_name)
    except Exception as e:
        return {'error': f'Generate vibe failed: {e}'}

    if not run.tracks:
        return {'error': 'No tracks found for query'}

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    # Save profile
    query_json = json.dumps({'query': query, 'n': n})
    created_at = time.time()
    track_count = len(run.tracks)
    
    cursor.execute(
        """
        INSERT OR REPLACE INTO vibe_profiles (name, query_json, created_at, track_count)
        VALUES (?, ?, ?, ?)
        """,
        (safe_name, query_json, created_at, track_count)
    )
    
    # Clear existing tracks for this vibe
    cursor.execute("DELETE FROM vibe_tracks WHERE vibe_name = ?", (safe_name,))
    
    # Save tracks with position — deduplicate by (artist, title) and track_id
    track_values = []
    seen_track_ids: set = set()
    seen_artist_title: set = set()
    pos = 1
    for track in run.tracks:
        key = (track.artist.lower().strip(), track.title.lower().strip())
        if key in seen_artist_title:
            continue
        seen_artist_title.add(key)
        cursor.execute("SELECT track_id FROM tracks WHERE filepath = ?", (track.path,))
        row = cursor.fetchone()
        if row:
            tid = row[0]
            if tid in seen_track_ids:
                continue
            seen_track_ids.add(tid)
            track_values.append((safe_name, tid, pos))
            pos += 1

    if track_values:
        cursor.executemany(
            """
            INSERT OR IGNORE INTO vibe_tracks (vibe_name, track_id, position)
            VALUES (?, ?, ?)
            """,
            track_values,
        )
    
    conn.commit()
    conn.close()
    
    return {
        'status': 'success',
        'name': safe_name,
        'query': query,
        'track_count': track_count,
        'created_at': created_at,
        'run_uuid': run.uuid,
    }


def list_vibes() -> List[Dict[str, Any]]:
    """
    List all saved vibes.
    
    Returns:
        List of vibe profile dicts
    """
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name, query_json, created_at, track_count FROM vibe_profiles ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    
    vibes = []
    for row in rows:
        name, query_json, created_at, track_count = row
        query_data = json.loads(query_json) if query_json else {}
        
        vibes.append({
            'name': name,
            'query': query_data.get('query', ''),
            'n': query_data.get('n', 0),
            'track_count': track_count,
            'created_at': created_at
        })
    
    return vibes


def build_vibe(name: str) -> Dict[str, Any]:
    """
    Build M3U8 playlist file for a vibe.
    
    Args:
        name: Vibe name
        
    Returns:
        Dict with status and file path
    """
    # Read vibe tracks from database
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT t.filepath, t.artist, t.title, t.duration, vt.position
        FROM vibe_tracks vt
        JOIN tracks t ON vt.track_id = t.track_id
        WHERE vt.vibe_name = ?
        ORDER BY vt.position
        """,
        (name,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {'error': f'No tracks found for vibe "{name}"'}
    
    # Create vibes directory
    VIBES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate M3U8 content
    m3u8_path = VIBES_DIR / f"{name}.m3u8"
    
    m3u8_lines = ['#EXTM3U']
    
    for row in rows:
        filepath, artist, title, duration, position = row
        
        # #EXTINF: duration, artist - title
        duration_int = int(duration) if duration else -1
        extinf = f"#EXTINF:{duration_int},{artist} - {title}"
        m3u8_lines.append(extinf)
        
        # Absolute path to file
        m3u8_lines.append(str(filepath))
    
    # Write M3U8
    try:
        with open(m3u8_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(m3u8_lines))
        
        return {
            'status': 'success',
            'name': name,
            'track_count': len(rows),
            'm3u8_path': str(m3u8_path)
        }
    except Exception as e:
        return {'error': f'Failed to write M3U8: {e}'}


def materialize_vibe(name: str, mode: str = 'hardlink') -> Dict[str, Any]:
    """
    Materialize a vibe as a folder with file links.
    
    Args:
        name: Vibe name
        mode: Link mode ('hardlink', 'symlink', 'shortcut')
        
    Returns:
        Dict with status and stats
    """
    if get_write_mode() != "apply_allowed":
        return {'error': 'LYRA_WRITE_MODE must be apply_allowed to materialize vibes'}
    
    if mode not in ['hardlink', 'symlink', 'shortcut']:
        return {'error': f'Invalid mode: {mode}'}
    
    # Read vibe tracks from database
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT t.filepath, vt.position
        FROM vibe_tracks vt
        JOIN tracks t ON vt.track_id = t.track_id
        WHERE vt.vibe_name = ?
        ORDER BY vt.position
        """,
        (name,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {'error': f'No tracks found for vibe "{name}"'}
    
    # Create vibe folder
    vibe_folder = VIBES_DIR / name
    vibe_folder.mkdir(parents=True, exist_ok=True)
    
    # Copy M3U8 into folder
    m3u8_source = VIBES_DIR / f"{name}.m3u8"
    m3u8_dest = vibe_folder / f"{name}.m3u8"
    
    if m3u8_source.exists():
        try:
            import shutil
            shutil.copy2(str(m3u8_source), str(m3u8_dest))
        except Exception as e:
            print(f"Warning: Could not copy M3U8: {e}")
    
    # Create links
    stats = {'created': 0, 'missing': 0, 'errors': 0, 'skipped': 0}
    
    for row in rows:
        filepath, position = row
        source_path = Path(filepath)
        
        if not source_path.exists():
            stats['missing'] += 1
            continue
        
        # Generate link filename: 001 - Original Filename.ext
        link_name = f"{position:03d} - {source_path.name}"
        link_path = vibe_folder / link_name
        
        # Skip if link already exists and points to correct file
        if link_path.exists():
            if mode == 'hardlink':
                # Check if it's the same file (inode comparison)
                try:
                    if os.path.samefile(str(source_path), str(link_path)):
                        stats['skipped'] += 1
                        continue
                    else:
                        # Different file, remove old link
                        link_path.unlink()
                except Exception:
                    # Can't compare, just recreate
                    try:
                        link_path.unlink()
                    except Exception:
                        pass
            else:
                # For symlink/shortcut, just skip if exists
                stats['skipped'] += 1
                continue
        
        # Create link based on mode
        try:
            if mode == 'hardlink':
                os.link(str(source_path), str(link_path))
                stats['created'] += 1
            
            elif mode == 'symlink':
                if os.name == 'nt':
                    os.link(str(source_path), str(link_path))
                else:
                    os.symlink(str(source_path), str(link_path))
                stats['created'] += 1
            
            elif mode == 'shortcut':
                # Windows .lnk shortcut (requires pywin32 or manual creation)
                # For now, prefer hardlink on Windows and symlink elsewhere.
                try:
                    if os.name == 'nt':
                        os.link(str(source_path), str(link_path))
                    else:
                        os.symlink(str(source_path), str(link_path))
                    stats['created'] += 1
                except Exception:
                    # Fallback to hardlink if symlink fails.
                    try:
                        os.link(str(source_path), str(link_path))
                        stats['created'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"Error creating link for {source_path.name}: {e}")
        
        except FileExistsError:
            stats['skipped'] += 1
        except Exception as e:
            stats['errors'] += 1
            print(f"Error creating link for {source_path.name}: {e}")
    
    return {
        'status': 'success',
        'name': name,
        'folder': str(vibe_folder),
        'mode': mode,
        'stats': stats
    }


def refresh_vibes(vibe_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Refresh vibe(s) by re-running search and updating database.
    
    Args:
        vibe_name: Specific vibe to refresh, or None for all
        
    Returns:
        Dict with refresh stats
    """
    if get_write_mode() != "apply_allowed":
        return {'error': 'LYRA_WRITE_MODE must be apply_allowed to refresh vibes'}
    
    # Get vibes to refresh
    vibes_to_refresh = []
    
    if vibe_name:
        # Refresh specific vibe
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, query_json FROM vibe_profiles WHERE name = ?",
            (vibe_name,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {'error': f'Vibe "{vibe_name}" not found'}
        
        name, query_json = row
        query_data = json.loads(query_json) if query_json else {}
        vibes_to_refresh.append((name, query_data.get('query', ''), query_data.get('n', 200)))
    else:
        # Refresh all vibes
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT name, query_json FROM vibe_profiles")
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            name, query_json = row
            query_data = json.loads(query_json) if query_json else {}
            vibes_to_refresh.append((name, query_data.get('query', ''), query_data.get('n', 200)))
    
    # Refresh each vibe
    results = []
    for name, query, n in vibes_to_refresh:
        result = save_vibe(name, query, n)
        results.append({'name': name, 'result': result})
        
        # Rebuild M3U8
        if result.get('status') == 'success':
            build_result = build_vibe(name)
            result['m3u8'] = build_result
    
    return {
        'status': 'success',
        'refreshed': len(results),
        'results': results
    }


def delete_vibe(name: str, delete_materialized: bool = False) -> Dict[str, Any]:
    """
    Delete a vibe profile.
    
    Args:
        name: Vibe name
        delete_materialized: Also delete materialized folder
        
    Returns:
        Dict with status
    """
    if get_write_mode() != "apply_allowed":
        return {'error': 'LYRA_WRITE_MODE must be apply_allowed to delete vibes'}
    
    # Delete from database
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM vibe_profiles WHERE name = ?", (name,))
    cursor.execute("DELETE FROM vibe_tracks WHERE vibe_name = ?", (name,))
    
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    
    if deleted_rows == 0:
        return {'error': f'Vibe "{name}" not found'}
    
    # Delete M3U8 file
    m3u8_path = VIBES_DIR / f"{name}.m3u8"
    if m3u8_path.exists():
        try:
            m3u8_path.unlink()
        except Exception as e:
            print(f"Warning: Could not delete M3U8: {e}")
    
    # Delete materialized folder if requested
    if delete_materialized:
        vibe_folder = VIBES_DIR / name
        if vibe_folder.exists():
            try:
                import shutil
                shutil.rmtree(str(vibe_folder))
            except Exception as e:
                return {
                    'status': 'partial',
                    'message': f'Deleted vibe but failed to delete folder: {e}'
                }
    
    return {
        'status': 'success',
        'name': name,
        'deleted_materialized': delete_materialized
    }
