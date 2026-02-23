"""Name cleaner for Lyra Oracle - removes junk from track titles and filenames."""

from __future__ import annotations

import re
from typing import Dict, Tuple
from pathlib import Path

# Patterns to remove from titles (case-insensitive)
JUNK_PATTERNS = [
    # YouTube junk
    r'\(official\s+(music\s+)?video\)',
    r'\[official\s+(music\s+)?video\]',
    r'\(official\s+audio\)',
    r'\[official\s+audio\]',
    r'\(lyric\s+video\)',
    r'\[lyric\s+video\]',
    r'\(music\s+video\)',
    r'\[music\s+video\]',
    
    # Quality indicators
    r'\(hq\)',
    r'\[hq\]',
    r'\(hd\)',
    r'\[hd\]',
    r'\(4k\s*remaster(?:ed)?\)',
    r'\[4k\s*remaster(?:ed)?\]',
    r'\(4k\)',
    r'\[4k\]',
    r'\bremaster(?:ed)?\b',
    r'1080p',
    r'720p',
    r'4k',
    
    # YouTube IDs (11 chars in brackets/parens at end)
    r'\[[a-zA-Z0-9_-]{11}\]$',
    r'\([a-zA-Z0-9_-]{11}\)$',
    
    # Common suffixes
    r'\(audio\)',
    r'\[audio\]',
    r'\(explicit\)',
    r'\[explicit\]',
    
    # Year patterns at end (but keep in album)
    r'\(\d{4}\)$',
    r'\[\d{4}\]$',
]

# Artist name patterns to clean
ARTIST_PATTERNS = [
    r'\s*-\s*topic$',  # "Artist - Topic"
    r'vevo$',  # "ArtistVEVO"
]

# Album patterns
ALBUM_PATTERNS = [
    r'\s*\(deluxe\s+edition\)',
    r'\s*\[deluxe\s+edition\]',
    r'\s*\(remaster(?:ed)?\)',
    r'\s*\[remaster(?:ed)?\]',
]


def clean_title(title: str) -> str:
    """
    Remove junk patterns from track title.
    
    Args:
        title: Original track title
        
    Returns:
        Cleaned title
    """
    if not title:
        return title
    
    cleaned = title
    
    # Apply all junk patterns
    for pattern in JUNK_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' -_')
    
    return cleaned or title  # Return original if we cleaned everything


def clean_artist(artist: str) -> str:
    """
    Remove junk patterns from artist name.
    
    Args:
        artist: Original artist name
        
    Returns:
        Cleaned artist name
    """
    if not artist:
        return artist
    
    cleaned = artist
    
    # Apply artist-specific patterns
    for pattern in ARTIST_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' -_')
    
    return cleaned or artist


def clean_album(album: str, keep_edition: bool = True) -> str:
    """
    Clean album name.
    
    Args:
        album: Original album name
        keep_edition: If False, removes "Deluxe Edition" etc
        
    Returns:
        Cleaned album name
    """
    if not album:
        return album
    
    cleaned = album
    
    if not keep_edition:
        for pattern in ALBUM_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' -_')
    
    return cleaned or album


def clean_filename(filename: str) -> str:
    """
    Clean a filename stem (without extension).
    
    Extracts artist/title if present, cleans both, returns cleaned filename.
    
    Args:
        filename: Original filename (stem, no extension)
        
    Returns:
        Cleaned filename
    """
    if not filename:
        return filename
    
    # Try to extract artist - title format
    if ' - ' in filename:
        parts = filename.split(' - ', 1)
        if len(parts) == 2:
            artist = clean_artist(parts[0])
            title = clean_title(parts[1])
            return f"{artist} - {title}"
    
    # No artist separator, just clean as title
    return clean_title(filename)


def parse_filename(filename: str) -> Dict[str, str]:
    """
    Parse filename into artist/title/album components.
    
    Handles formats:
    - "Artist - Title"
    - "Artist - Album - Title"
    - "Title"
    
    Args:
        filename: Filename stem (without extension)
        
    Returns:
        Dict with 'artist', 'title', 'album' keys (values may be None)
    """
    result = {'artist': None, 'title': None, 'album': None}
    
    if not filename:
        return result
    
    # Split on ' - '
    parts = [p.strip() for p in filename.split(' - ') if p.strip()]
    
    if len(parts) == 0:
        return result
    elif len(parts) == 1:
        # Just title
        result['title'] = clean_title(parts[0])
    elif len(parts) == 2:
        # Artist - Title
        result['artist'] = clean_artist(parts[0])
        result['title'] = clean_title(parts[1])
    else:
        # Artist - Album - Title (or more parts)
        result['artist'] = clean_artist(parts[0])
        result['album'] = clean_album(parts[1])
        result['title'] = clean_title(' - '.join(parts[2:]))
    
    return result


def clean_metadata(meta: Dict[str, str]) -> Dict[str, str]:
    """
    Clean all metadata fields in place.
    
    Args:
        meta: Metadata dict with 'artist', 'title', 'album' keys
        
    Returns:
        Cleaned metadata dict (same object, modified)
    """
    if 'artist' in meta and meta['artist']:
        meta['artist'] = clean_artist(meta['artist'])
    
    if 'title' in meta and meta['title']:
        meta['title'] = clean_title(meta['title'])
    
    if 'album' in meta and meta['album']:
        meta['album'] = clean_album(meta['album'])
    
    return meta


def suggest_rename(file_path: Path) -> Tuple[Path, bool]:
    """
    Suggest a cleaned filename for a file.
    
    Args:
        file_path: Original file path
        
    Returns:
        Tuple of (new_path, needs_rename)
    """
    stem = file_path.stem
    cleaned_stem = clean_filename(stem)
    
    if stem == cleaned_stem:
        return file_path, False
    
    new_path = file_path.parent / f"{cleaned_stem}{file_path.suffix}"
    return new_path, True
