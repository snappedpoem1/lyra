"""Vibe system for Lyra Oracle - semantic playlist management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import time

from oracle.config import VIBES_FOLDER
from oracle.db.schema import get_connection, get_write_mode
from oracle.search import search

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIBES_DIR = VIBES_FOLDER


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
    
    # Run semantic search
    try:
        results = search(query, n=n)
    except Exception as e:
        return {'error': f'Search failed: {e}'}
    
    if not results:
        return {'error': 'No tracks found for query'}
    
    # Store in database
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    # Save profile
    query_json = json.dumps({'query': query, 'n': n})
    created_at = time.time()
    track_count = len(results)
    
    cursor.execute(
        """
        INSERT OR REPLACE INTO vibe_profiles (name, query_json, created_at, track_count)
        VALUES (?, ?, ?, ?)
        """,
        (safe_name, query_json, created_at, track_count)
    )
    
    # Clear existing tracks for this vibe
    cursor.execute("DELETE FROM vibe_tracks WHERE vibe_name = ?", (safe_name,))
    
    # Save tracks with position
    for idx, result in enumerate(results, start=1):
        track_id = result.get('track_id')
        if track_id:
            cursor.execute(
                """
                INSERT INTO vibe_tracks (vibe_name, track_id, position)
                VALUES (?, ?, ?)
                """,
                (safe_name, track_id, idx)
            )
    
    conn.commit()
    conn.close()
    
    return {
        'status': 'success',
        'name': safe_name,
        'query': query,
        'track_count': track_count,
        'created_at': created_at
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
