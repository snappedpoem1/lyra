"""Download processor for Lyra Oracle - finds and lists downloads.

Organization is now handled by beets via ``oracle import``.
This module retains discovery and listing utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from oracle.scanner import AUDIO_EXTS, extract_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
STAGING_DIR = PROJECT_ROOT / "staging"


def find_new_downloads() -> List[Path]:
    """Find all audio files in downloads/ and staging/ directories.

    Returns:
        Sorted list of audio file paths.
    """
    files: List[Path] = []
    for directory in [DOWNLOADS_DIR, STAGING_DIR]:
        if not directory.exists():
            continue
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTS:
                files.append(file_path)
    return sorted(files)


def list_downloads(show_metadata: bool = False) -> List[Dict]:
    """List all downloads with optional metadata preview.

    Args:
        show_metadata: Extract and show metadata from tags.

    Returns:
        List of file info dicts.
    """
    files = find_new_downloads()
    results: List[Dict] = []

    for file_path in files:
        info: Dict = {
            "path": str(file_path),
            "name": file_path.name,
            "size_mb": file_path.stat().st_size / (1024 * 1024),
            "folder": file_path.parent.name,
        }

        if show_metadata:
            meta = extract_metadata(file_path)
            info["metadata"] = meta

        results.append(info)

    return results
