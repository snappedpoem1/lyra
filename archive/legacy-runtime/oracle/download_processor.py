"""Download processor for Lyra Oracle — discovers and organises downloads.

All new files in A:\\Staging go through guard + name_cleaner and land in the
canonical library layout: {LIBRARY_BASE}/{Artist}/{Album}/{NN}_{Title}.ext
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from oracle.config import DOWNLOADS_FOLDER, LIBRARY_BASE, STAGING_FOLDER
from oracle.name_cleaner import target_path as _make_target_path
from oracle.scanner import AUDIO_EXTS, extract_metadata

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Legacy constants kept for any callers that import them directly
DOWNLOADS_DIR = DOWNLOADS_FOLDER
STAGING_DIR   = STAGING_FOLDER


def find_new_downloads() -> List[Path]:
    """Find all audio files in downloads/ and staging/ directories.

    Returns:
        Sorted list of audio file paths.
    """
    files: List[Path] = []
    for directory in [DOWNLOADS_FOLDER, STAGING_FOLDER]:
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


def organize(
    library_path: Optional[Path] = None,
    dry_run: bool = True,
    source_dirs: Optional[List[Path]] = None,
) -> Dict:
    """Move audio files from staging/downloads into the canonical library layout.

    Layout: ``{library_path}/{Artist}/{Album}/{NN}_{Title}.ext``

    Metadata is read from file tags via :func:`oracle.scanner.extract_metadata`.
    All naming goes through :mod:`oracle.name_cleaner` so the result always
    matches Picard's output.

    Args:
        library_path: Destination library root (defaults to ``LIBRARY_BASE``).
        dry_run:      When ``True`` (default), only reports what would happen.
        source_dirs:  Which folders to scan.  Defaults to
                      ``[STAGING_FOLDER, DOWNLOADS_FOLDER]``.

    Returns:
        Dict with counts: ``moved``, ``skipped``, ``errors``, ``files``.
    """
    lib = library_path or LIBRARY_BASE
    sources = source_dirs or [STAGING_FOLDER, DOWNLOADS_FOLDER]

    summary: Dict = {"moved": 0, "skipped": 0, "errors": 0, "files": []}

    for source_dir in sources:
        if not source_dir.exists():
            logger.debug("organize: source dir not found, skipping: %s", source_dir)
            continue

        for audio_file in sorted(source_dir.rglob("*")):
            if not audio_file.is_file():
                continue
            if audio_file.suffix.lower() not in AUDIO_EXTS:
                continue

            try:
                meta = extract_metadata(audio_file)
                artist     = meta.get("artist", "") or "Unknown Artist"
                title      = meta.get("title", "") or audio_file.stem
                album      = meta.get("album", "") or "Unknown Album"
                track_num_raw = meta.get("track_number")
                track_num: Optional[int] = (
                    int(track_num_raw) if track_num_raw and str(track_num_raw).isdigit() else None
                )

                dest = _make_target_path(
                    lib,
                    artist,
                    album,
                    track_num,
                    title,
                    audio_file.suffix.lstrip("."),
                )

                entry: Dict = {
                    "src": str(audio_file),
                    "dest": str(dest),
                    "artist": artist,
                    "title": title,
                }

                if dest.exists():
                    logger.info("  SKIP (exists): %s", dest.name)
                    summary["skipped"] += 1
                    entry["action"] = "skipped"
                else:
                    verb = "Would move" if dry_run else "Moving"
                    logger.info("  %s: %s → %s/%s/%s",
                                verb, audio_file.name,
                                dest.parent.parent.name,
                                dest.parent.name,
                                dest.name)
                    if not dry_run:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(audio_file), str(dest))
                    summary["moved"] += 1
                    entry["action"] = "would_move" if dry_run else "moved"

                summary["files"].append(entry)

            except Exception as exc:
                logger.error("  ERROR processing %s: %s", audio_file, exc)
                summary["errors"] += 1
                summary["files"].append({
                    "src": str(audio_file),
                    "action": "error",
                    "error": str(exc),
                })

    logger.info(
        "organize complete: moved=%d skipped=%d errors=%d%s",
        summary["moved"],
        summary["skipped"],
        summary["errors"],
        " (dry run)" if dry_run else "",
    )
    return summary

