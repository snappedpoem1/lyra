"""Data importers for Lyra Oracle.

Exposes helpers for importing external data (Spotify extended streaming
history, etc.) into the lyra_registry.db without requiring callers to
deal with the root-level spotify_import.py script directly.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# spotify_import.py lives at the project root (not inside any package).
# Insert the root onto sys.path so we can import it cleanly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from spotify_import import (  # type: ignore
        SCHEMA_SQL,
        find_history_files,
        import_streaming_history as _raw_import_streaming_history,
    )
    _SPOTIFY_IMPORT_AVAILABLE = True
except ImportError as _err:
    logger.debug("[importers] spotify_import not available: %s", _err)
    find_history_files = None  # type: ignore
    _SPOTIFY_IMPORT_AVAILABLE = False


def run_spotify_history_import() -> Dict[str, Any]:
    """Import Spotify extended streaming history JSON files into spotify_history.

    Finds ``Streaming_History_Audio_*.json`` files in the known locations
    (``Spotify Extended Streaming History/``, ``data/spotify/``, etc.),
    creates the necessary tables if they don't exist, and upserts all
    records using ``INSERT OR IGNORE`` to prevent duplicates.

    Returns:
        Stats dict: ``{files, streams, skipped, errors}``

    Raises:
        RuntimeError: When ``spotify_import.py`` cannot be located.
    """
    if not _SPOTIFY_IMPORT_AVAILABLE:
        raise RuntimeError(
            "spotify_import.py not found at project root. "
            "Ensure it exists at C:\\MusicOracle\\spotify_import.py"
        )

    from oracle.db.schema import get_connection

    conn = get_connection(timeout=30.0)
    try:
        # Ensure spotify_import tables exist in the main DB
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        stats = _raw_import_streaming_history(conn)
    finally:
        conn.close()

    return stats


__all__ = ["find_history_files", "run_spotify_history_import"]
