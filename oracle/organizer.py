"""Folder organizer for generating canonical library paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Dict

from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection


def _sanitize_filename(text: str) -> str:
    """
    Sanitize text for use in filenames/folders.
    
    Removes invalid Windows characters: < > : " / \\ | ? *
    Also removes leading/trailing dots and spaces.
    """
    if not text:
        return "Unknown"
    
    # Replace invalid chars with underscore
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', text)
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    # Collapse multiple spaces/underscores
    sanitized = re.sub(r'[ _]+', ' ', sanitized)
    
    # Limit length to prevent path issues
    if len(sanitized) > 200:
        sanitized = sanitized[:200].strip()
    
    return sanitized or "Unknown"


def generate_target_path(
    track_id: str,
    preset: str = "artist_album",
    base_library: str = str(LIBRARY_BASE)
) -> Optional[Path]:
    """
    Generate ideal canonical path for a track based on preset.
    
    Presets:
        - artist_album: {Artist}/{Album} ({Year})/{##} - {Title}.{ext}
        - remix: {Artist}/Remixes/{Title} ({Remixer}).{ext}
        - live: {Artist}/Live/{Album} ({Year})/{##} - {Title}.{ext}
        - compilation: Compilations/{Album}/{##} - {Artist} - {Title}.{ext}
        - various: Various Artists/{Album}/{##} - {Artist} - {Title}.{ext}
        - flat_artist: {Artist}/{##} - {Title}.{ext}
    
    Args:
        track_id: Track ID to generate path for
        preset: Organization preset
        base_library: Root library path
        
    Returns:
        Path object or None if track not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT artist, title, album, year, filepath, version_type
        FROM tracks WHERE track_id = ?
        """,
        (track_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    artist, title, album, year, filepath, version_type = row
    
    # Track/disc numbers not in schema - default to 00
    track_number = None
    disc_number = None
    
    # Get file extension
    ext = Path(filepath).suffix if filepath else ".m4a"
    
    # Sanitize components
    artist_safe = _sanitize_filename(artist or "Unknown Artist")
    title_safe = _sanitize_filename(title or "Unknown Title")
    album_safe = _sanitize_filename(album or "Unknown Album")
    
    # Format track number
    track_num_str = f"{track_number:02d}" if track_number else "00"
    disc_num_str = f"{disc_number:02d}" if disc_number and disc_number > 1 else None
    
    # Base path
    base = Path(base_library)
    
    # Build path based on preset and version_type
    if preset == "artist_album":
        # Standard: Artist/Album (Year)/## - Title.ext
        if version_type == "remix":
            # Remixes go in special folder
            if album and album.lower() != "unknown album":
                folder = base / artist_safe / "Remixes" / album_safe
            else:
                folder = base / artist_safe / "Remixes"
            filename = f"{track_num_str} - {title_safe}{ext}"
        
        elif version_type == "live":
            # Live recordings
            if album and album.lower() != "unknown album":
                if year:
                    folder = base / artist_safe / "Live" / f"{album_safe} ({year})"
                else:
                    folder = base / artist_safe / "Live" / album_safe
            else:
                folder = base / artist_safe / "Live"
            filename = f"{track_num_str} - {title_safe}{ext}"
        
        elif version_type == "cover":
            # Cover versions
            folder = base / artist_safe / "Covers"
            filename = f"{track_num_str} - {title_safe}{ext}"
        
        elif version_type == "junk":
            # Junk goes to quarantine or special folder
            folder = base.parent / "_Quarantine" / "Junk"
            filename = f"{title_safe}{ext}"
        
        else:
            # Original or special versions: standard layout
            if album and album.lower() != "unknown album":
                # Check for "Various Artists" or compilation
                if artist and (
                    artist.lower() in ["various artists", "various", "compilation"] or
                    (album and "compilation" in album.lower())
                ):
                    folder = base / "Various Artists" / album_safe
                    filename = f"{track_num_str} - {artist_safe} - {title_safe}{ext}"
                else:
                    # Standard artist/album layout
                    if year:
                        album_folder = f"{album_safe} ({year})"
                    else:
                        album_folder = album_safe
                    
                    # Multi-disc support
                    if disc_num_str:
                        folder = base / artist_safe / album_folder / f"Disc {disc_num_str}"
                    else:
                        folder = base / artist_safe / album_folder
                    
                    filename = f"{track_num_str} - {title_safe}{ext}"
            else:
                # No album info: Artist/## - Title.ext
                folder = base / artist_safe
                filename = f"{track_num_str} - {title_safe}{ext}"
    
    elif preset == "remix":
        # Force remix layout
        if album and album.lower() != "unknown album":
            folder = base / artist_safe / "Remixes" / album_safe
        else:
            folder = base / artist_safe / "Remixes"
        filename = f"{track_num_str} - {title_safe}{ext}"
    
    elif preset == "live":
        # Force live layout
        if album and album.lower() != "unknown album":
            if year:
                folder = base / artist_safe / "Live" / f"{album_safe} ({year})"
            else:
                folder = base / artist_safe / "Live" / album_safe
        else:
            folder = base / artist_safe / "Live"
        filename = f"{track_num_str} - {title_safe}{ext}"
    
    elif preset == "compilation":
        # Compilations/{Album}/{##} - {Artist} - {Title}.ext
        folder = base / "Compilations" / album_safe
        filename = f"{track_num_str} - {artist_safe} - {title_safe}{ext}"
    
    elif preset == "various":
        # Various Artists/{Album}/{##} - {Artist} - {Title}.ext
        folder = base / "Various Artists" / album_safe
        filename = f"{track_num_str} - {artist_safe} - {title_safe}{ext}"
    
    elif preset == "flat_artist":
        # Flat: Artist/{##} - {Title}.ext
        folder = base / artist_safe
        filename = f"{track_num_str} - {title_safe}{ext}"
    
    else:
        # Unknown preset: fallback to artist_album
        return generate_target_path(track_id, preset="artist_album", base_library=base_library)
    
    return folder / filename


def get_relocation_candidates(
    library_path: str = str(LIBRARY_BASE),
    preset: str = "artist_album",
    limit: int = 0
) -> Dict:
    """
    Find tracks that need relocation based on canonical paths.
    
    Args:
        library_path: Library root
        preset: Organization preset
        limit: Max tracks to check (0 = all)
        
    Returns:
        {
            "total": int,
            "needs_relocation": int,
            "candidates": [{track_id, current_path, target_path, reason}, ...]
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if limit > 0:
        cursor.execute("SELECT track_id, filepath FROM tracks WHERE filepath IS NOT NULL LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT track_id, filepath FROM tracks WHERE filepath IS NOT NULL")
    
    rows = cursor.fetchall()
    conn.close()
    
    candidates = []
    
    for track_id, current_path in rows:
        if not current_path:
            continue
        
        target_path = generate_target_path(track_id, preset=preset, base_library=library_path)
        
        if target_path is None:
            continue
        
        current = Path(current_path).resolve()
        target = target_path.resolve()
        
        # Check if relocation needed
        if current != target:
            candidates.append({
                "track_id": track_id,
                "current_path": str(current),
                "target_path": str(target),
                "reason": f"Canonical path differs (preset: {preset})"
            })
    
    return {
        "total": len(rows),
        "needs_relocation": len(candidates),
        "candidates": candidates
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    import sys
    if len(sys.argv) > 1:
        track_id = sys.argv[1]
        preset = sys.argv[2] if len(sys.argv) > 2 else "artist_album"
        
        target = generate_target_path(track_id, preset=preset)
        if target:
            print(f"Target path for track {track_id} (preset={preset}):")
            print(f"  {target}")
        else:
            print(f"Track {track_id} not found")
    else:
        print("Usage: python -m oracle.organizer <track_id> [preset]")
