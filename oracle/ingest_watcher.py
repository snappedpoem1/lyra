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
<<<<<<< HEAD
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv

load_dotenv(override=True)

=======
import os
import sqlite3
import shutil
import time
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

>>>>>>> fc77b41 (Update workspace state and diagnostics)
logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus"}
POLL_INTERVAL = 10  # seconds between sweeps
STABLE_SECONDS = 10  # file must not change size for this long before ingesting
<<<<<<< HEAD
PROJECT_ROOT = Path(__file__).resolve().parents[1]
=======
# Files older than this are assumed stable; skip stability wait in --once mode
ALREADY_STABLE_AGE = 30  # seconds
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LOCK_FILE = PROJECT_ROOT / ".ingest_watcher.lock"


class _WatcherLock:
    """PID-file lock that prevents duplicate watcher processes.

    Uses exclusive file creation so only one process can hold the lock.
    On Windows, opening with O_CREAT|O_EXCL is atomic and achieves mutual
    exclusion without requiring fcntl (Unix-only).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._held: bool = False

    def acquire(self) -> bool:
        """Return True if lock acquired, False if another instance is running."""
        # If stale lock exists from a dead process, remove it first
        if self._path.exists():
            try:
                pid = int(self._path.read_text().strip())
                # Check if that PID is still alive
                if sys.platform == "win32":
                    import ctypes
                    handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
                    alive = handle != 0
                    if handle:
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    alive = os.path.exists(f"/proc/{pid}")
                if not alive:
                    self._path.unlink(missing_ok=True)
            except Exception:
                self._path.unlink(missing_ok=True)

        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self._held = True
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def release(self) -> None:
        if self._held:
            self._path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> "_WatcherLock":
        return self

    def __exit__(self, *_) -> None:
        self.release()


def _sanitize_component(value: str, fallback: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*]', "_", (value or "").strip())
    clean = re.sub(r"\s+", " ", clean).strip(". ")
    return clean or fallback


def _primary_album_artist(artist: str) -> str:
    raw = (artist or "").strip()
    if not raw:
        return "Unknown Artist"
    split_patterns = [
        r"\s*,\s*",
        r"\s+feat\.?\s+",
        r"\s+featuring\s+",
        r"\s+ft\.?\s+",
        r"\s+x\s+",
        r"\s+with\s+",
    ]
    primary = raw
    for pattern in split_patterns:
        parts = re.split(pattern, primary, maxsplit=1, flags=re.IGNORECASE)
        if parts and parts[0].strip():
            primary = parts[0].strip()
            if primary != raw:
                break
    return primary or "Unknown Artist"


def _extract_album_track(filepath: Path) -> tuple[Optional[str], Optional[int]]:
    try:
        import mutagen
        audio = mutagen.File(str(filepath), easy=True)
        if not audio:
            return None, None
        album = None
        track_num = None
        album_values = audio.get("album", [])
        if album_values:
            album = str(album_values[0]).strip() or None
        track_values = audio.get("tracknumber", [])
        if track_values:
            raw = str(track_values[0]).split("/")[0].strip()
            if raw.isdigit():
                track_num = int(raw)
        return album, track_num
    except Exception:
        return None, None
>>>>>>> fc77b41 (Update workspace state and diagnostics)


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


<<<<<<< HEAD
=======
def _extract_tag(tags: dict, *keys: str, fallback: str = "") -> str:
    """Safely extract a tag value from mutagen tags (ID3 or Vorbis)."""
    for key in keys:
        val = tags.get(key)
        if val is None:
            continue
        # mutagen ID3 frames are subscriptable; Vorbis returns lists
        try:
            text = str(val[0]) if hasattr(val, "__getitem__") else str(val)
        except (IndexError, TypeError):
            continue
        if text.strip():
            return text.strip()
    return fallback


>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
<<<<<<< HEAD
            artist = str(tags.get("TPE1", tags.get("artist", [""]))[0] if hasattr(tags.get("TPE1", None), "__getitem__") else tags.get("artist", [""])[0]) if "TPE1" in tags or "artist" in tags else ""
            title = str(tags.get("TIT2", tags.get("title", [filepath.stem]))[0] if hasattr(tags.get("TIT2", None), "__getitem__") else tags.get("title", [filepath.stem])[0]) if "TIT2" in tags or "title" in tags else filepath.stem
        result = guard_acquisition(artist=artist, title=title)
        return {"allowed": result.allowed, "reason": result.rejection_reason}
=======
            artist = _extract_tag(tags, "TPE1", "artist")
            title = _extract_tag(tags, "TIT2", "title", fallback=filepath.stem)
        result = guard_acquisition(artist=artist, title=title)
        return {
            "allowed": result.allowed,
            "reason": result.rejection_reason,
            "artist": result.artist or artist,
            "title": result.title or title,
            "confidence": float(result.confidence or 0.0),
        }
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    except Exception as e:
        logger.warning(f"Guard check error (rejecting): {e}")
        return {"allowed": False, "reason": f"guard error: {e}"}


def _move_to_library(filepath: Path, library_dir: Path) -> Path:
<<<<<<< HEAD
    """Move file to library root (scanner will organize later)."""
    dest = library_dir / filepath.name
    # Handle filename collision
    if dest.exists():
        stem = filepath.stem
        suffix = filepath.suffix
        dest = library_dir / f"{stem}_{int(time.time())}{suffix}"
=======
    """Move file to Artist/Album/Song layout."""
    guard = _guard_check(filepath)
    artist = _sanitize_component(
        _primary_album_artist(guard.get("artist", "")),
        "Unknown Artist",
    )
    title = _sanitize_component(guard.get("title", "") or filepath.stem, filepath.stem)
    album_tag, track_num = _extract_album_track(filepath)
    album = _sanitize_component(album_tag or "Singles", "Singles")
    prefix = f"{track_num:02d} - " if track_num else ""
    filename = f"{prefix}{title}{filepath.suffix}"
    dest = library_dir / artist / album / filename
    # Handle filename collision
    if dest.exists():
        stem = dest.stem
        suffix = filepath.suffix
        dest = dest.parent / f"{stem}_{int(time.time())}{suffix}"
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(filepath), str(dest))
    return dest


<<<<<<< HEAD
def _move_file(filepath: Path, library_dir: Path) -> Optional[Path]:
    """Guard check + move to library. Returns dest path on success, None on rejection."""
=======
def _mark_queue_completed(artist: str, title: str) -> None:
    if not artist or not title:
        return
    from oracle.db.schema import get_connection
    attempts = 4
    for attempt in range(1, attempts + 1):
        conn = get_connection(timeout=10.0)
        try:
            conn.execute(
                """
                UPDATE acquisition_queue
                SET status='completed', completed_at=datetime('now'), error=NULL
                WHERE lower(trim(artist)) = lower(trim(?))
                  AND (
                      lower(trim(title)) = lower(trim(?))
                      OR lower(trim(title)) LIKE lower(trim(?)) || '%'
                      OR lower(trim(?)) LIKE lower(trim(title)) || '%'
                  )
                  AND status IN ('downloaded', 'pending')
                """,
                (artist, title, title, title),
            )
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < attempts:
                time.sleep(0.05 * attempt)
                continue
            logger.warning("[INGEST] Queue completion update failed for %s - %s: %s", artist, title, exc)
            return
        finally:
            conn.close()


def _move_file(filepath: Path, library_dir: Path) -> Optional[tuple[Path, dict]]:
    """Guard check + move to library. Returns (dest, guard) on success, None on rejection."""
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    logger.info(f"[INGEST] Processing: {filepath.name}")

    guard = _guard_check(filepath)
    if not guard["allowed"]:
        logger.warning(f"[INGEST] REJECTED by guard: {filepath.name} — {guard['reason']}")
        q_dir = library_dir.parent / "_Quarantine" / "Junk"
        q_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(filepath), str(q_dir / filepath.name))
<<<<<<< HEAD
        except Exception:
            pass
=======
        except Exception as exc:
            logger.error("[INGEST] Failed to quarantine rejected file %s: %s", filepath, exc)
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        return None

    try:
        dest = _move_to_library(filepath, library_dir)
        logger.info(f"[INGEST] Moved: {dest.name}")
<<<<<<< HEAD
        return dest
=======
        return dest, guard
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
<<<<<<< HEAD
=======
    moved_guard: List[dict] = []
>>>>>>> fc77b41 (Update workspace state and diagnostics)

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
<<<<<<< HEAD
            dest = _move_file(path, library_dir)
            if dest:
                moved.append(dest)
=======
            payload = _move_file(path, library_dir)
            if payload:
                dest, guard = payload
                moved.append(dest)
                moved_guard.append(guard)
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        except Exception as e:
            logger.error(f"[INGEST] Unhandled error on {path.name}: {e}")

    if not moved:
        return 0

    # Batch scan + index once for all moved files
<<<<<<< HEAD
=======
    scan_ok = False
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    try:
        from oracle.scanner import scan_paths
        result = scan_paths(moved)
        logger.info(f"[INGEST] Batch scan: {result}")
<<<<<<< HEAD
=======
        scan_ok = True
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    except Exception as e:
        logger.error(f"[INGEST] Scan failed: {e}")
        return len(moved)

<<<<<<< HEAD
=======
    index_ok = False
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    try:
        from oracle.indexer import index_track_ids
        track_ids = result.get("track_ids", []) if isinstance(result, dict) else []
        result = index_track_ids(track_ids) if track_ids else {"indexed": 0, "failed": 0, "scored": 0}
        logger.info(f"[INGEST] Batch index: {result}")
<<<<<<< HEAD
    except Exception as e:
        logger.error(f"[INGEST] Index failed: {e}")

=======
        index_ok = True
    except Exception as e:
        logger.error(f"[INGEST] Index failed: {e}")

    if scan_ok and index_ok:
        for guard in moved_guard:
            _mark_queue_completed(guard.get("artist", ""), guard.get("title", ""))

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    logger.info(f"[INGEST] Done. {len(moved)} file(s) ingested.")
    return len(moved)


def run_watcher(once: bool = False) -> None:
<<<<<<< HEAD
    """Main loop. If once=True, does one sweep and exits."""
=======
    """Main loop. If once=True, does one sweep and exits.

    Lock enforcement: only one watcher may run at a time. A second invocation
    will exit immediately with a warning rather than creating a race condition.
    """
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

<<<<<<< HEAD
=======
    lock = _WatcherLock(_LOCK_FILE)
    if not lock.acquire():
        logger.warning(
            "[WATCHER] Another watcher instance is already running. "
            "Exiting to prevent race conditions."
        )
        return

    try:
        _run_watcher_locked(once=once)
    finally:
        lock.release()


def _run_watcher_locked(once: bool = False) -> None:
    """Internal watcher body — called after lock is acquired."""
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
<<<<<<< HEAD
=======
    now = time.time()
>>>>>>> fc77b41 (Update workspace state and diagnostics)

    def _sweep_all() -> int:
        total = 0
        for d in watch_dirs:
            total += _sweep(d, library_dir, prev_sizes, ingested)
        return total

    if once:
<<<<<<< HEAD
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
=======
        # Collect audio files and check whether any are too new to be stable.
        audio_files: List[Path] = []
        needs_wait = False
        for d in watch_dirs:
            for path in sorted(d.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                audio_files.append(path)
                try:
                    size = path.stat().st_size
                    mtime = path.stat().st_mtime
                    prev_sizes[str(path)] = size
                    # File modified very recently → might still be writing
                    if (now - mtime) < ALREADY_STABLE_AGE:
                        needs_wait = True
                except OSError:
                    pass

        if not audio_files:
            logger.info("[WATCHER] No audio files found. Nothing to ingest.")
            return

        if needs_wait:
            logger.info(f"[WATCHER] {len(audio_files)} file(s) found. Waiting {STABLE_SECONDS}s for stability...")
            time.sleep(STABLE_SECONDS)
        else:
            logger.info(f"[WATCHER] {len(audio_files)} file(s) found (already stable). Ingesting immediately.")

>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
