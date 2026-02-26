"""Ingest Watcher -- polls downloads/ and staging/ dirs and auto-ingests
completed files via beets.

Runs as a background daemon.  When new audio files appear and are stable
(size unchanged for 10 s), the watcher runs:

    guard check -> beets import (auto-tag + move) -> scan -> index -> score

Usage:
    python -m oracle.ingest_watcher          # run as daemon
    python -m oracle.ingest_watcher --once   # process current files and exit
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus"}
POLL_INTERVAL = 10  # seconds between sweeps
STABLE_SECONDS = 10  # file must not change size for this long before ingesting
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
                if sys.platform == "win32":
                    import ctypes
                    # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is sufficient to test liveness.
                    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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


def _has_audio_files(directory: Path) -> bool:
    """Check if a directory contains any audio files."""
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            return True
    return False


def _mark_queue_completed(artist: str, title: str) -> None:
    """Mark matching acquisition_queue rows as completed."""
    import sqlite3

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
            logger.warning(
                "[INGEST] Queue completion update failed for %s - %s: %s",
                artist, title, exc,
            )
            return
        finally:
            conn.close()


def _reconcile_downloaded_queue_rows() -> int:
    """Mark downloaded queue items completed when the track exists in library DB."""
    import sqlite3

    from oracle.db.schema import get_connection
    attempts = 4
    for attempt in range(1, attempts + 1):
        conn = get_connection(timeout=10.0)
        try:
            cur = conn.execute(
                """
                UPDATE acquisition_queue
                SET status='completed', completed_at=datetime('now'), error=NULL
                WHERE status='downloaded'
                  AND EXISTS (
                    SELECT 1
                    FROM tracks t
                    WHERE t.status='active'
                      AND (
                        lower(trim(t.artist)) = lower(trim(acquisition_queue.artist))
                        OR lower(trim(t.artist)) LIKE lower(trim(acquisition_queue.artist)) || '%'
                        OR lower(trim(acquisition_queue.artist)) LIKE lower(trim(t.artist)) || '%'
                      )
                      AND (
                        lower(trim(t.title)) = lower(trim(acquisition_queue.title))
                        OR lower(trim(t.title)) LIKE lower(trim(acquisition_queue.title)) || '%'
                        OR lower(trim(acquisition_queue.title)) LIKE lower(trim(t.title)) || '%'
                      )
                  )
                """
            )
            conn.commit()
            return int(cur.rowcount or 0)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < attempts:
                time.sleep(0.05 * attempt)
                continue
            logger.warning("[INGEST] Queue reconciliation failed: %s", exc)
    return 0


def _requeue_stale_downloaded_rows(max_age_minutes: int = 45) -> int:
    """Re-queue downloaded rows that never materialized in the active library.

    This prevents queue deadlocks where rows remain `downloaded` forever after
    a partial ingest crash or source mismatch.
    """
    import sqlite3

    from oracle.db.schema import get_connection
    attempts = 4
    for attempt in range(1, attempts + 1):
        conn = get_connection(timeout=10.0)
        try:
            cur = conn.execute(
                """
                UPDATE acquisition_queue
                SET status='pending',
                    retry_count=COALESCE(retry_count, 0) + 1,
                    error='stale downloaded row re-queued by watcher reconciliation'
                WHERE status='downloaded'
                  AND datetime(COALESCE(completed_at, added_at))
                      < datetime('now', '-' || ? || ' minutes')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM tracks t
                    WHERE t.status='active'
                      AND (
                        lower(trim(t.artist)) = lower(trim(acquisition_queue.artist))
                        OR lower(trim(t.artist)) LIKE lower(trim(acquisition_queue.artist)) || '%'
                        OR lower(trim(acquisition_queue.artist)) LIKE lower(trim(t.artist)) || '%'
                      )
                      AND (
                        lower(trim(t.title)) = lower(trim(acquisition_queue.title))
                        OR lower(trim(t.title)) LIKE lower(trim(acquisition_queue.title)) || '%'
                        OR lower(trim(acquisition_queue.title)) LIKE lower(trim(t.title)) || '%'
                      )
                  )
                """,
                (str(int(max_age_minutes)),),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < attempts:
                time.sleep(0.05 * attempt)
                continue
            logger.warning("[INGEST] Stale downloaded requeue failed: %s", exc)
            return 0
        finally:
            conn.close()


def _sweep(watch_dirs: List[Path],
           prev_sizes: Dict[str, int],
           ingested: Set[str]) -> int:
    """One sweep -- collect stable directories with audio, import via beets.

    Stable files are detected, then beets handles guard + move + tag.
    Post-import scan+index happens inside ``beets_import_and_ingest``.
    """
    from oracle.integrations.beets_import import beets_import_and_ingest

    total_imported = 0

    for watch_dir in watch_dirs:
        # Find files that are stable (size unchanged since last check)
        ready_files: List[Path] = []
        for path in sorted(watch_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            key = str(path)
            if key in ingested:
                continue
            if not _is_stable(path, prev_sizes):
                continue
            ready_files.append(path)
            ingested.add(key)

        if not ready_files:
            continue

        logger.info(
            "[INGEST] %d stable file(s) in %s -- importing via beets",
            len(ready_files), watch_dir,
        )

        # Flat files in staging come from Qobuz/acquirers with good tags;
        # use --singletons --noautotag to avoid MusicBrainz match failures.
        has_subdirs = any(p.is_dir() for p in watch_dir.iterdir()
                         if not p.name.startswith("_"))
        kwargs: Dict[str, bool] = {}
        if not has_subdirs:
            kwargs["singleton"] = True
            kwargs["no_autotag"] = True

        try:
            result = beets_import_and_ingest(watch_dir, **kwargs)
            imported = result.get("imported", 0)
            quarantined = result.get("quarantined", 0)
            errors = result.get("errors", 0)
            logger.info(
                "[INGEST] Beets: %d imported, %d quarantined, %d errors",
                imported, quarantined, errors,
            )
            total_imported += imported
            completed = _reconcile_downloaded_queue_rows()
            if completed:
                logger.info("[INGEST] Queue reconcile: %d downloaded item(s) marked completed", completed)
            requeued = _requeue_stale_downloaded_rows(max_age_minutes=45)
            if requeued:
                logger.info("[INGEST] Queue reconcile: %d stale downloaded item(s) re-queued", requeued)
        except Exception as exc:
            logger.error("[INGEST] Beets import failed: %s", exc)

    return total_imported


def run_watcher(once: bool = False) -> None:
    """Main loop.  If *once* is True, does one sweep and exits.

    Lock enforcement: only one watcher may run at a time.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

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
    """Internal watcher body -- called after lock is acquired."""
    downloads_dir = _get_downloads_dir()
    staging_dir = PROJECT_ROOT / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    watch_dirs = [d for d in [downloads_dir, staging_dir] if d.exists()]

    logger.info("[WATCHER] Watching: %s", ", ".join(str(d) for d in watch_dirs))
    logger.info("[WATCHER] Library dir: %s", _get_library_dir())

    prev_sizes: Dict[str, int] = {}
    ingested: Set[str] = set()
    now = time.time()

    if once:
        # Pre-populate sizes for stability check
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
                    if (now - mtime) < ALREADY_STABLE_AGE:
                        needs_wait = True
                except OSError:
                    pass

        if not audio_files:
            logger.info("[WATCHER] No audio files found. Nothing to ingest.")
            return

        if needs_wait:
            logger.info(
                "[WATCHER] %d file(s) found. Waiting %ds for stability...",
                len(audio_files), STABLE_SECONDS,
            )
            time.sleep(STABLE_SECONDS)
        else:
            logger.info(
                "[WATCHER] %d file(s) found (already stable). Ingesting immediately.",
                len(audio_files),
            )

        n = _sweep(watch_dirs, prev_sizes, ingested)
        logger.info("[WATCHER] Done. Ingested %d file(s).", n)
        return

    logger.info("[WATCHER] Polling every %ds. Ctrl+C to stop.", POLL_INTERVAL)
    while True:
        try:
            n = _sweep(watch_dirs, prev_sizes, ingested)
            if n:
                logger.info("[WATCHER] Ingested %d file(s) this sweep.", n)
        except KeyboardInterrupt:
            logger.info("[WATCHER] Stopped.")
            break
        except Exception as exc:
            logger.error("[WATCHER] Sweep error: %s", exc)
        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lyra ingest watcher daemon")
    parser.add_argument("--once", action="store_true", help="Process current files and exit")
    args = parser.parse_args()
    run_watcher(once=args.once)


if __name__ == "__main__":
    main()
