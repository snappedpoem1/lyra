"""
Recover corrupted zeroed audio files from a library and optionally restore files.

This is a generic maintenance utility. It does not assume any artist, album, or
machine-specific paths.

Usage:
    python scripts/fix_zeroed_tracks.py --library "<library path>"
    python scripts/fix_zeroed_tracks.py --library "<library path>" --apply
    python scripts/fix_zeroed_tracks.py --library "<library path>" --restore-src "<file>" --restore-dest "<file>" --apply
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

AUDIO_EXT = {".flac", ".mp3", ".m4a", ".opus", ".ogg", ".wav"}


def is_zeroed(path: Path) -> bool:
    """Return True if the first 8 bytes are all null."""
    try:
        with path.open("rb") as fh:
            return fh.read(8) == b"\x00" * 8
    except OSError:
        return False


def find_zeroed_files(library: Path) -> list[Path]:
    """Return all audio files in the library whose content begins with null bytes."""
    zeroed: list[Path] = []
    for candidate in library.rglob("*"):
        if candidate.suffix.lower() in AUDIO_EXT and is_zeroed(candidate):
            zeroed.append(candidate)
    return sorted(zeroed)


def purge_from_db(paths: list[Path], dry_run: bool) -> int:
    """Remove track + dependent rows for each path. Returns count purged."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from oracle.db.schema import get_connection

    conn = get_connection()
    cursor = conn.cursor()
    purged = 0
    for path in paths:
        cursor.execute(
            "SELECT track_id FROM tracks WHERE lower(filepath) = lower(?)",
            (str(path),),
        )
        row = cursor.fetchone()
        if not row:
            log.warning("Not in DB: %s", path)
            continue
        track_id = row[0]
        if dry_run:
            log.info("[DRY] Would delete track_id=%s  %s", track_id, path.name)
        else:
            for table in ("embeddings", "track_scores", "errors", "tracks"):
                cursor.execute(f"DELETE FROM {table} WHERE track_id = ?", (track_id,))
            conn.commit()
            log.info("Deleted track_id=%s  %s", track_id, path.name)
        purged += 1
    conn.close()
    return purged


def move_to_rejected(files: list[Path], library: Path, rejected_corrupted: Path, dry_run: bool) -> int:
    """Move zeroed files to a rejected folder, preserving the relative subpath."""
    moved = 0
    for src in files:
        try:
            rel = src.relative_to(library)
        except ValueError:
            rel = Path(src.name)
        dest = rejected_corrupted / rel
        if dry_run:
            log.info("[DRY] Move -> %s", dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            log.info("Moved -> %s", dest)
        moved += 1
    return moved


def restore_file(restore_src: Path | None, restore_dest: Path | None, dry_run: bool) -> bool:
    """Restore a single file from a source path back into the library."""
    if not restore_src or not restore_dest:
        return False
    if not restore_src.exists():
        log.warning("Restore source not found: %s", restore_src)
        return False
    if dry_run:
        log.info("[DRY] Restore -> %s", restore_dest)
        return True
    restore_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(restore_src), str(restore_dest))
    log.info("Restored -> %s", restore_dest)
    return True


def reindex_paths(paths: list[Path]) -> None:
    """Scan and reindex any recovered files that now exist on disk."""
    if not paths:
        return
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from oracle.scanner import scan_paths
    from oracle.indexer import index_track_ids

    for path in paths:
        if not path.exists() or is_zeroed(path):
            continue
        log.info("Scanning recovered file: %s", path)
        result = scan_paths([path])
        track_ids: list[str] = result.get("track_ids", [])  # type: ignore[assignment]
        if track_ids:
            index_result = index_track_ids(track_ids, force_reindex=True)
            log.info("Re-index result: %s", index_result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge zeroed tracks and optionally restore/reindex recovered files")
    parser.add_argument("--library", required=True, help="Library root to scan")
    parser.add_argument("--rejected-corrupted", help="Destination folder for moved corrupted files")
    parser.add_argument("--restore-src", help="Optional source file to restore")
    parser.add_argument("--restore-dest", help="Optional destination path for restored file")
    parser.add_argument("--reindex-path", action="append", default=[], help="Path to re-scan and re-index after recovery; may be supplied multiple times")
    parser.add_argument("--apply", action="store_true", help="Actually make changes (default is dry-run)")
    args = parser.parse_args()

    dry_run = not args.apply
    library = Path(args.library)
    rejected_corrupted = Path(args.rejected_corrupted) if args.rejected_corrupted else (library.parent / "Rejected" / "Corrupted")
    restore_src = Path(args.restore_src) if args.restore_src else None
    restore_dest = Path(args.restore_dest) if args.restore_dest else None
    reindex_targets = [Path(path) for path in args.reindex_path]
    if restore_dest:
        reindex_targets.append(restore_dest)

    if dry_run:
        log.info("=== DRY RUN - pass --apply to make changes ===")

    log.info("Scanning library for zeroed audio files...")
    zeroed = find_zeroed_files(library)
    log.info("Found %d zeroed files", len(zeroed))

    by_album: dict[Path, list[str]] = defaultdict(list)
    for item in zeroed:
        by_album[item.parent].append(item.name)
    for album, names in sorted(by_album.items()):
        log.info("  (%d) %s", len(names), album)

    log.info("--- Purging %d tracks from DB ---", len(zeroed))
    purged = purge_from_db(zeroed, dry_run=dry_run)
    log.info("Purged %d DB records", purged)

    log.info("--- Moving zeroed files to %s ---", rejected_corrupted)
    moved = move_to_rejected(zeroed, library=library, rejected_corrupted=rejected_corrupted, dry_run=dry_run)
    log.info("Moved %d files", moved)

    if restore_src and restore_dest:
        log.info("--- Restoring file ---")
        restored = restore_file(restore_src, restore_dest, dry_run=dry_run)
        log.info("Restore: %s", "OK" if restored else "SKIPPED")

    if dry_run:
        log.info("=== DRY RUN COMPLETE - re-run with --apply to execute ===")
        return

    if reindex_targets:
        log.info("--- Re-indexing recovered files ---")
        reindex_paths(reindex_targets)

    if by_album:
        log.info("")
        log.info("=== ALBUMS REQUIRING RE-ACQUISITION ===")
        for album in sorted(by_album.keys()):
            try:
                parts = album.relative_to(library).parts
            except ValueError:
                parts = album.parts
            artist = parts[0].replace("_", " ") if parts else "?"
            album_name = parts[1].replace("_", " ") if len(parts) > 1 else "?"
            log.info("  oracle acquire waterfall --artist %r --album %r", artist, album_name)


if __name__ == "__main__":
    main()
