"""Ingest Watcher — polls downloads/ dir and auto-ingests completed files.

Runs as a background daemon. When a new audio file appears in the downloads
directory (and hasn't changed size for 10s, indicating complete download),
it runs the full ingest pipeline: scan → guard check → move to library →
index → score → update DB.

Usage:
    python -m oracle.ingest_watcher          # run as daemon
    python -m oracle.ingest_watcher --once   # process current files and exit
"""

from __future__ import annotations

import argparse
import logging
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus"}
POLL_INTERVAL = 10  # seconds between sweeps
STABLE_SECONDS = 10  # file must not change size for this long before ingesting
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _get_downloads_dir() -> Path:
    from oracle.config import DOWNLOADS_FOLDER
    p = Path(DOWNLOADS_FOLDER)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_library_dir() -> Path:
    from oracle.config import LIBRARY_BASE
    return Path(LIBRARY_BASE)


def _is_stable(path: Path, prev_sizes: Dict[str, int]) -> bool:
    """Return True if file size hasn't changed since last check."""
    key = str(path)
    try:
        size = path.stat().st_size
    except OSError:
        return False

    prev = prev_sizes.get(key)
    prev_sizes[key] = size

    return prev is not None and prev == size


def _guard_check(filepath: Path) -> dict:
    """Run acquisition guard on a downloaded file."""
    try:
        from oracle.acquirers.guard import guard_acquisition
        import mutagen
        audio = mutagen.File(str(filepath))
        artist = ""
        title = filepath.stem
        if audio and hasattr(audio, "tags") and audio.tags:
            tags = audio.tags
            artist = str(tags.get("TPE1", tags.get("artist", [""]))[0] if hasattr(tags.get("TPE1", None), "__getitem__") else tags.get("artist", [""])[0]) if "TPE1" in tags or "artist" in tags else ""
            title = str(tags.get("TIT2", tags.get("title", [filepath.stem]))[0] if hasattr(tags.get("TIT2", None), "__getitem__") else tags.get("title", [filepath.stem])[0]) if "TIT2" in tags or "title" in tags else filepath.stem
        result = guard_acquisition(artist=artist, title=title)
        return {"allowed": result.allowed, "reason": result.rejection_reason}
    except Exception as e:
        logger.warning(f"Guard check error (rejecting): {e}")
        return {"allowed": False, "reason": f"guard error: {e}"}


def _move_to_library(filepath: Path, library_dir: Path) -> Path:
    """Move file to library root (scanner will organize later)."""
    dest = library_dir / filepath.name
    # Handle filename collision
    if dest.exists():
        stem = filepath.stem
        suffix = filepath.suffix
        dest = library_dir / f"{stem}_{int(time.time())}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(filepath), str(dest))
    return dest


def _move_file(filepath: Path, library_dir: Path) -> Optional[Path]:
    """Guard check + move to library. Returns dest path on success, None on rejection."""
    logger.info(f"[INGEST] Processing: {filepath.name}")

    guard = _guard_check(filepath)
    if not guard["allowed"]:
        logger.warning(f"[INGEST] REJECTED by guard: {filepath.name} — {guard['reason']}")
        q_dir = library_dir.parent / "_Quarantine" / "Junk"
        q_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(filepath), str(q_dir / filepath.name))
        except Exception:
            pass
        return None

    try:
        dest = _move_to_library(filepath, library_dir)
        logger.info(f"[INGEST] Moved: {dest.name}")
        return dest
    except Exception as e:
        logger.error(f"[INGEST] Move failed: {e}")
        return None


def _sweep(downloads_dir: Path, library_dir: Path,
           prev_sizes: Dict[str, int], ingested: Set[str]) -> int:
    """One sweep of the downloads directory.

    Moves all stable files into the library, then runs scan+index once as a batch.
    CLAP model is loaded once per sweep, not once per file.
    """
    moved: List[Path] = []

    for path in sorted(downloads_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        key = str(path)
        if key in ingested:
            continue
        if not _is_stable(path, prev_sizes):
            continue  # Still downloading

        ingested.add(key)
        try:
            dest = _move_file(path, library_dir)
            if dest:
                moved.append(dest)
        except Exception as e:
            logger.error(f"[INGEST] Unhandled error on {path.name}: {e}")

    if not moved:
        return 0

    # Batch scan + index once for all moved files
    try:
        from oracle.scanner import scan_paths
        result = scan_paths(moved)
        logger.info(f"[INGEST] Batch scan: {result}")
    except Exception as e:
        logger.error(f"[INGEST] Scan failed: {e}")
        return len(moved)

    try:
        from oracle.indexer import index_track_ids
        track_ids = result.get("track_ids", []) if isinstance(result, dict) else []
        result = index_track_ids(track_ids) if track_ids else {"indexed": 0, "failed": 0, "scored": 0}
        logger.info(f"[INGEST] Batch index: {result}")
    except Exception as e:
        logger.error(f"[INGEST] Index failed: {e}")

    logger.info(f"[INGEST] Done. {len(moved)} file(s) ingested.")
    return len(moved)


def run_watcher(once: bool = False) -> None:
    """Main loop. If once=True, does one sweep and exits."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    downloads_dir = _get_downloads_dir()
    staging_dir = PROJECT_ROOT / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    library_dir = _get_library_dir()

    # Watch both downloads/ (slskd T2) and staging/ (T3 yt-dlp post-flight)
    watch_dirs = [d for d in [downloads_dir, staging_dir] if d.exists()]

    logger.info(f"[WATCHER] Watching: {', '.join(str(d) for d in watch_dirs)}")
    logger.info(f"[WATCHER] Library dir: {library_dir}")

    prev_sizes: Dict[str, int] = {}
    ingested: Set[str] = set()

    def _sweep_all() -> int:
        total = 0
        for d in watch_dirs:
            total += _sweep(d, library_dir, prev_sizes, ingested)
        return total

    if once:
        # Prime sizes from all watch dirs, wait one interval, then ingest stable files
        for d in watch_dirs:
            for path in sorted(d.rglob("*")):
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                    try:
                        prev_sizes[str(path)] = path.stat().st_size
                    except OSError:
                        pass
        logger.info(f"[WATCHER] Waiting {STABLE_SECONDS}s for files to stabilize...")
        time.sleep(STABLE_SECONDS)
        n = _sweep_all()
        logger.info(f"[WATCHER] Done. Ingested {n} file(s).")
        return

    logger.info(f"[WATCHER] Polling every {POLL_INTERVAL}s. Ctrl+C to stop.")
    while True:
        try:
            n = _sweep_all()
            if n:
                logger.info(f"[WATCHER] Ingested {n} file(s) this sweep.")
        except KeyboardInterrupt:
            logger.info("[WATCHER] Stopped.")
            break
        except Exception as e:
            logger.error(f"[WATCHER] Sweep error: {e}")
        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lyra ingest watcher daemon")
    parser.add_argument("--once", action="store_true", help="Process current files and exit")
    args = parser.parse_args()
    run_watcher(once=args.once)


if __name__ == "__main__":
    main()
