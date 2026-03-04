"""
fix_zeroed_tracks.py — Purge zeroed (null-byte) FLAC files from library + DB,
restore the Bayside track from Rejected, re-index Poppy + Bayside.

Usage:
    python scripts/fix_zeroed_tracks.py [--dry-run]
    python scripts/fix_zeroed_tracks.py --apply
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

LIBRARY = Path(r"A:\Music")
REJECTED_CORRUPTED = Path(r"A:\Rejected\Corrupted")
BAYSIDE_SRC = Path(
    r"A:\Rejected\Duplicates\Bayside\[standalone_recordings]\02_Sick,_Sick,_Sick.flac"
)
BAYSIDE_DEST = Path(
    r"A:\Music\Bayside\[standalone_recordings]\02_Sick,_Sick,_Sick.flac"
)

AUDIO_EXT = {".flac", ".mp3", ".m4a", ".opus", ".ogg", ".wav"}


def is_zeroed(path: Path) -> bool:
    """Return True if the first 8 bytes are all null."""
    try:
        with path.open("rb") as fh:
            return fh.read(8) == b"\x00" * 8
    except OSError:
        return False


def find_zeroed_files() -> list[Path]:
    """Return all audio files in LIBRARY whose content is null bytes."""
    zeroed: list[Path] = []
    for f in LIBRARY.rglob("*"):
        if f.suffix.lower() in AUDIO_EXT and is_zeroed(f):
            zeroed.append(f)
    return sorted(zeroed)


def purge_from_db(paths: list[Path], dry_run: bool) -> int:
    """Remove track + dependent rows for each path. Returns count purged."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from oracle.db.schema import get_connection

    conn = get_connection()
    c = conn.cursor()
    purged = 0
    for p in paths:
        # DB may store paths with different drive-letter casing (e.g. A:\music vs A:\Music)
        c.execute(
            "SELECT track_id FROM tracks WHERE lower(filepath) = lower(?)",
            (str(p),),
        )
        row = c.fetchone()
        if not row:
            log.warning("Not in DB: %s", p)
            continue
        tid = row[0]
        if dry_run:
            log.info("[DRY] Would delete track_id=%s  %s", tid, p.name)
        else:
            for table in ("embeddings", "track_scores", "errors", "tracks"):
                c.execute(f"DELETE FROM {table} WHERE track_id = ?", (tid,))
            conn.commit()
            log.info("Deleted track_id=%s  %s", tid, p.name)
        purged += 1
    conn.close()
    return purged


def move_to_rejected(files: list[Path], dry_run: bool) -> int:
    """Move zeroed files to REJECTED_CORRUPTED, preserving Artist/Album subpath."""
    moved = 0
    for src in files:
        # Preserve relative path under LIBRARY
        try:
            rel = src.relative_to(LIBRARY)
        except ValueError:
            rel = Path(src.name)
        dest = REJECTED_CORRUPTED / rel
        if dry_run:
            log.info("[DRY] Move -> %s", dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            log.info("Moved -> %s", dest)
        moved += 1
    return moved


def restore_bayside(dry_run: bool) -> bool:
    """Move Bayside file from Rejected back to library."""
    if not BAYSIDE_SRC.exists():
        log.warning("Bayside source not found: %s", BAYSIDE_SRC)
        return False
    if dry_run:
        log.info("[DRY] Restore Bayside -> %s", BAYSIDE_DEST)
        return True
    BAYSIDE_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(BAYSIDE_SRC), str(BAYSIDE_DEST))
    log.info("Restored Bayside -> %s", BAYSIDE_DEST)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge zeroed tracks and re-index recovered files")
    parser.add_argument("--apply", action="store_true", help="Actually make changes (default is dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        log.info("=== DRY RUN — pass --apply to make changes ===")

    # 1. Find all zeroed files
    log.info("Scanning library for zeroed audio files...")
    zeroed = find_zeroed_files()
    log.info("Found %d zeroed files:", len(zeroed))
    from collections import defaultdict
    by_album: dict[Path, list[str]] = defaultdict(list)
    for f in zeroed:
        by_album[f.parent].append(f.name)
    for album, names in sorted(by_album.items()):
        log.info("  (%d) %s", len(names), album)

    # 2. Purge from DB
    log.info("--- Purging %d tracks from DB ---", len(zeroed))
    purged = purge_from_db(zeroed, dry_run=dry_run)
    log.info("Purged %d DB records", purged)

    # 3. Move zeroed files to Rejected/Corrupted
    log.info("--- Moving zeroed files to %s ---", REJECTED_CORRUPTED)
    moved = move_to_rejected(zeroed, dry_run=dry_run)
    log.info("Moved %d files", moved)

    # 4. Restore Bayside
    log.info("--- Restoring Bayside ---")
    ok = restore_bayside(dry_run=dry_run)
    log.info("Bayside restore: %s", "OK" if ok else "SKIPPED")

    if dry_run:
        log.info("=== DRY RUN COMPLETE — re-run with --apply to execute ===")
        return

    # 5. Re-index recovered/skipped files
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from oracle.db.schema import get_connection as _get_conn
    from oracle.scanner import scan_paths
    from oracle.indexer import index_track_ids

    # Poppy: already in DB (scanned), just needs embedding
    poppy = Path(r"A:\Music\Poppy\Negative_Spaces\13_new_way_out.flac")
    if poppy.exists() and not is_zeroed(poppy):
        conn = _get_conn()
        c = conn.cursor()
        c.execute("SELECT track_id FROM tracks WHERE lower(filepath) = lower(?)", (str(poppy),))
        row = c.fetchone()
        conn.close()
        if row:
            log.info("Re-indexing Poppy (track_id=%s)...", row[0])
            res = index_track_ids([row[0]], force_reindex=True)
            log.info("Poppy index result: %s", res)
        else:
            log.warning("Poppy not in DB, scanning first...")
            r = scan_paths([poppy])
            tids: list[str] = r.get("track_ids", [])  # type: ignore[assignment]
            if tids:
                res = index_track_ids(tids, force_reindex=True)
                log.info("Poppy index result: %s", res)

    # Bayside: new to DB (was in Rejected during scan), needs full scan+index
    if BAYSIDE_DEST.exists():
        log.info("Scanning Bayside...")
        r2 = scan_paths([BAYSIDE_DEST])
        tids2: list[str] = r2.get("track_ids", [])  # type: ignore[assignment]
        log.info("Bayside scan: %s  track_ids=%d", r2, len(tids2))
        if tids2:
            res2 = index_track_ids(tids2, force_reindex=True)
            log.info("Bayside index result: %s", res2)

    # 6. Report albums needing re-acquisition
    log.info("")
    log.info("=== ALBUMS REQUIRING RE-ACQUISITION ===")
    for album in sorted(by_album.keys()):
        # Folder name pattern: A:\Music\{Artist}\{Album}
        parts = album.relative_to(LIBRARY).parts
        artist = parts[0].replace("_", " ") if parts else "?"
        album_name = parts[1].replace("_", " ") if len(parts) > 1 else "?"
        log.info("  oracle acquire waterfall --artist %r --album %r", artist, album_name)


if __name__ == "__main__":
    main()
