"""High-performance async music library scanner using os.scandir and asyncio."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from mutagen import File as MutagenFile

# Configuration
AUDIO_EXTS = {".mp3", ".flac"}
DB_PATH = Path(__file__).resolve().parents[1] / "oracle_library.db"


@dataclass
class TrackMetadata:
    """Container for extracted track metadata."""
    filepath: str
    artist: str
    album: str
    title: str
    duration: Optional[float] = None
    content_hash: Optional[str] = None


def _extract_metadata_sync(file_path: Path) -> Optional[TrackMetadata]:
    """Extract metadata synchronously for use in thread pool."""
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if not audio or not audio.tags:
            return None

        artist = audio.tags.get("artist", [None])[0] or ""
        album = audio.tags.get("album", [None])[0] or ""
        title = audio.tags.get("title", [None])[0] or ""

        if not title:
            title = file_path.stem

        duration = None
        if audio.info and hasattr(audio.info, "length"):
            duration = float(audio.info.length)

        content_hash = _compute_file_hash(file_path)

        return TrackMetadata(
            filepath=str(file_path),
            artist=artist.strip(),
            album=album.strip(),
            title=title.strip(),
            duration=duration,
            content_hash=content_hash,
        )
    except Exception as exc:
        import logging
        logging.getLogger("async_scanner").warning("Metadata extraction failed for %s: %s", file_path, exc)
        return None


def _compute_file_hash(file_path: Path) -> str:
    """Fast file hash for deduplication."""
    stat = file_path.stat()
    hasher = hashlib.sha256()
    hasher.update(str(stat.st_size).encode())

    # Small files: full content, Large files: head + tail
    if stat.st_size <= 8 * 1024 * 1024:
        with file_path.open("rb") as f:
            hasher.update(f.read())
    else:
        chunk_size = 4 * 1024 * 1024
        with file_path.open("rb") as f:
            hasher.update(f.read(chunk_size))
            f.seek(max(stat.st_size - chunk_size, 0))
            hasher.update(f.read(chunk_size))

    return hasher.hexdigest()


def _find_audio_files_sync(root: Path) -> List[Path]:
    """Find all audio files using os.scandir for speed."""
    audio_files: List[Path] = []

    def _scan_dir(directory: Path):
        try:
            with os.scandir(str(directory)) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            ext = Path(entry.name).suffix.lower()
                            if ext in AUDIO_EXTS:
                                audio_files.append(Path(entry.path))
                        elif entry.is_dir(follow_symlinks=False):
                            _scan_dir(Path(entry.path))
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass

    _scan_dir(root)
    return audio_files


def _init_database() -> None:
    """Initialize database schema with thread-local connection."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT UNIQUE NOT NULL,
            artist TEXT,
            album TEXT,
            title TEXT,
            duration REAL,
            content_hash TEXT,
            scanned_at REAL DEFAULT (strftime('%s', 'now')),
            updated_at REAL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_hash ON tracks(content_hash)")
    conn.commit()
    conn.close()


def _write_batch_sync(db_path: Path, metadata_list: List[Optional[TrackMetadata]]) -> Dict[str, int]:
    """Write metadata batch to database (thread-safe)."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")
    conn.execute("PRAGMA temp_store=MEMORY")

    stats = {"scanned": 0, "added": 0, "updated": 0, "errors": 0}

    for metadata in metadata_list:
        if metadata is None:
            stats["errors"] += 1
            continue

        stats["scanned"] += 1

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tracks WHERE filepath = ?", (metadata.filepath,))
            exists = cursor.fetchone()
            now = time.time()

            if exists:
                cursor.execute(
                    """
                    UPDATE tracks
                    SET artist = ?, album = ?, title = ?, duration = ?,
                        content_hash = ?, updated_at = ?
                    WHERE filepath = ?
                    """,
                    (metadata.artist, metadata.album, metadata.title, metadata.duration,
                     metadata.content_hash, now, metadata.filepath)
                )
                stats["updated"] += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO tracks (filepath, artist, album, title, duration, content_hash, scanned_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (metadata.filepath, metadata.artist, metadata.album, metadata.title,
                     metadata.duration, metadata.content_hash, now, now)
                )
                stats["added"] += 1
        except Exception as exc:
            stats["errors"] += 1
            import logging
            logging.getLogger("async_scanner").error("DB error for %s: %s", metadata.filepath, exc)

    conn.commit()
    conn.close()

    return stats


async def _extract_metadata_batch(file_paths: List[Path], executor: ThreadPoolExecutor) -> List[Optional[TrackMetadata]]:
    """Extract metadata from a batch of files in parallel."""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(executor, _extract_metadata_sync, fp) for fp in file_paths]
    return await asyncio.gather(*tasks)


async def scan_library_async(
    directory: str | Path,
    batch_size: int = 50,
    max_workers: int = 4,
) -> Dict[str, int]:
    """
    Async music library scanner.

    Args:
        directory: Root directory to scan for audio files.
        batch_size: Number of files to process per batch.
        max_workers: Number of thread pool workers for I/O-bound tasks.

    Returns:
        Dictionary with scan statistics: {scanned, added, updated, errors}
    """
    root = Path(directory).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    loop = asyncio.get_event_loop()

    # Find all audio files
    print(f"Scanning {root}...")
    audio_files = await loop.run_in_executor(None, _find_audio_files_sync, root)
    total_files = len(audio_files)

    if total_files == 0:
        print("No audio files found.")
        return {"scanned": 0, "added": 0, "updated": 0, "errors": 0}

    print(f"Found {total_files} audio files. Extracting metadata...")

    # Initialize database
    _init_database()

    stats = {"scanned": 0, "added": 0, "updated": 0, "errors": 0}

    # Process in batches with thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i in range(0, total_files, batch_size):
            batch = audio_files[i:i + batch_size]
            metadata_list = await _extract_metadata_batch(batch, executor)

            # Write batch using thread-safe function
            batch_stats = await loop.run_in_executor(
                executor, _write_batch_sync, DB_PATH, metadata_list
            )

            stats["scanned"] += batch_stats["scanned"]
            stats["added"] += batch_stats["added"]
            stats["updated"] += batch_stats["updated"]
            stats["errors"] += batch_stats["errors"]

            # Progress
            processed = min(i + batch_size, total_files)
            print(f"Progress: {processed}/{total_files} ({processed*100//total_files}%)")

    print("\nScan complete:")
    print(f"  Scanned: {stats['scanned']}")
    print(f"  Added:   {stats['added']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Errors:  {stats['errors']}")

    return stats


async def find_files_async(directory: str | Path) -> AsyncGenerator[Path, None]:
    """
    Async generator for finding audio files.

    Args:
        directory: Root directory to scan.

    Yields:
        Path objects for each audio file found.
    """
    root = Path(directory).resolve()

    async def _scan_dir(dir_path: Path):
        loop = asyncio.get_event_loop()

        def _scan():
            try:
                with os.scandir(str(dir_path)) as entries:
                    return [
                        (Path(entry.path), entry.is_dir(follow_symlinks=False))
                        for entry in entries
                        if not entry.name.startswith('.')
                    ]
            except (OSError, PermissionError):
                return []

        entries = await loop.run_in_executor(None, _scan)

        for path, is_dir in entries:
            if is_dir:
                async for result in _scan_dir(path):
                    yield result
            elif path.suffix.lower() in AUDIO_EXTS:
                yield path

    async for file_path in _scan_dir(root):
        yield file_path


def _main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Async high-performance music library scanner")
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing")
    parser.add_argument("--workers", type=int, default=4, help="Thread pool workers")
    args = parser.parse_args()

    asyncio.run(scan_library_async(args.directory, args.batch_size, args.workers))


if __name__ == "__main__":
    _main()