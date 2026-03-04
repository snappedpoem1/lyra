"""oracle/name_cleaner.py — single source of truth for all naming logic.

All modules (guard, scanner, normalizer, organizer, smart_pipeline, qobuz)
should import from here instead of duplicating regex.

Functions
---------
clean_artist(s)         → (primary_artist, [featured_artists])
clean_title(s)          → (clean_title, [featured_artists])
to_folder_name(s)       → filesystem-safe, spaces→underscores, max 100 chars
to_file_stem(n, title)  → Picard-style "01_Title_Name"
target_path(...)        → canonical library Path matching Picard layout
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Delegate to the authoritative implementations — no logic duplication
# ---------------------------------------------------------------------------
from oracle.normalizer import normalize_artist as _norm_artist
from oracle.normalizer import normalize_title as _norm_title

# Re-export the organizer helpers so callers don't need to know where they live
from oracle.organizer import _primary_album_artist, _sanitize_filename

# ---------------------------------------------------------------------------
# Windows path chars that are always illegal  (also includes forward slash,
# which Windows allows only as a path separator)
# ---------------------------------------------------------------------------
_WIN_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_artist(artist: str) -> Tuple[str, List[str]]:
    """Normalise an artist tag and extract any featured artists.

    Args:
        artist: Raw artist string from a file tag or DB field.

    Returns:
        Tuple of (primary_artist, [featured_artists]).
        primary_artist is never empty — returns "Unknown Artist" as fallback.
    """
    primary, featured = _norm_artist(artist or "")
    return primary or "Unknown Artist", featured


def clean_title(title: str) -> Tuple[str, List[str]]:
    """Clean a track title: remove feat., video cruft, duplicate prefixes.

    Args:
        title: Raw title string.

    Returns:
        Tuple of (clean_title, [featured_artists extracted from title]).
    """
    clean, featured = _norm_title(title or "")
    return clean or "Unknown Title", featured


def to_folder_name(s: str, max_length: int = 100) -> str:
    """Convert a string to a Picard-compatible folder/file component.

    - Strips Windows-illegal characters
    - Replaces spaces with underscores (matching Picard's default)
    - Collapses multiple underscores to one
    - Strips leading/trailing underscores and dots
    - Truncates to *max_length* characters

    Args:
        s:          Input string (artist name, album, title …).
        max_length: Maximum character length (default 100).

    Returns:
        Filesystem-safe string.
    """
    # First apply the standard organizer sanitisation (handles reserved names)
    s = _sanitize_filename(s, max_length=max_length + 50)

    # Convert spaces to underscores (Picard default)
    s = s.replace(" ", "_")

    # Drop remaining illegal characters
    s = _WIN_ILLEGAL.sub("", s)

    # Collapse repeated underscores
    s = re.sub(r"_+", "_", s)

    # Strip leading/trailing underscores and dots
    s = s.strip("_.")

    # Truncate
    if len(s) > max_length:
        s = s[:max_length].rstrip("_.")

    return s or "Unknown"


def to_file_stem(track_num: Optional[int], title: str) -> str:
    """Build a Picard-style file stem: ``NN_Title_Name``.

    Args:
        track_num: Track number (1-based).  None → no prefix.
        title:     Track title (will be run through to_folder_name).

    Returns:
        String like ``"03_Everlong"`` or ``"Everlong"`` if no track number.

    Examples::

        >>> to_file_stem(3, "Everlong")
        '03_Everlong'
        >>> to_file_stem(None, "Everlong")
        'Everlong'
    """
    title_part = to_folder_name(title)
    if track_num is None:
        return title_part
    return f"{track_num:02d}_{title_part}"


def target_path(
    library_base: Path,
    artist: str,
    album: str,
    track_num: Optional[int],
    title: str,
    ext: str,
) -> Path:
    """Build the canonical library path for a track.

    Matches Picard's default layout::

        {library_base}/{Artist}/{Album}/{NN}_{Title}.{ext}

    All components are passed through :func:`to_folder_name` so the result
    always matches what Picard would produce.

    Args:
        library_base: Root of the music library (e.g. ``Path("A:/Music")``).
        artist:       Primary artist name (feat. stripped internally).
        album:        Album name.
        track_num:    Track number; ``None`` if unknown.
        title:        Track title.
        ext:          File extension WITHOUT leading dot (e.g. ``"flac"``).

    Returns:
        :class:`pathlib.Path` for the target file.

    Examples::

        >>> target_path(Path("A:/Music"), "Brand New", "Deja Entendu",
        ...             3, "Sic Transit Gloria...Glory Fades", "flac")
        WindowsPath('A:/Music/Brand_New/Deja_Entendu/03_Sic_Transit_Gloria...Glory_Fades.flac')
    """
    primary_artist = _primary_album_artist(artist)

    artist_dir = to_folder_name(primary_artist)
    album_dir  = to_folder_name(album)
    stem       = to_file_stem(track_num, title)
    ext        = ext.lstrip(".").lower()

    return library_base / artist_dir / album_dir / f"{stem}.{ext}"
