"""Scheduler rib: embedded APScheduler running inside the Flask process.

This keeps background jobs available without requiring a separate worker
process. A cross-process lock is used by default so only one API process
starts embedded jobs on a host.
"""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path
from typing import Optional

from flask import Flask

logger = logging.getLogger(__name__)

_scheduler = None
_lock_fd: Optional[int] = None
_lock_path: Optional[Path] = None


def _scheduler_lock_enabled() -> bool:
    return os.getenv("LYRA_SCHEDULER_SINGLE_INSTANCE", "1").strip().lower() in {"1", "true", "yes", "on"}


def _scheduler_lock_file() -> Path:
    configured = os.getenv("LYRA_SCHEDULER_LOCK_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / ".lyra_scheduler.lock"


def _release_scheduler_process_lock() -> None:
    global _lock_fd, _lock_path
    try:
        if _lock_fd is not None:
            os.close(_lock_fd)
    except OSError:
        pass
    finally:
        _lock_fd = None
    try:
        if _lock_path and _lock_path.exists():
            _lock_path.unlink()
    except OSError:
        # Best effort cleanup; stale lock can be removed manually.
        pass
    finally:
        _lock_path = None


def _acquire_scheduler_process_lock() -> bool:
    """Acquire a filesystem lock so only one process starts embedded jobs."""
    global _lock_fd, _lock_path
    if _lock_fd is not None:
        return True

    lock_file = _scheduler_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError as exc:
        logger.warning("[scheduler] lock acquisition failed (%s); skipping embedded scheduler", exc)
        return False

    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("utf-8", errors="replace"))
    except OSError:
        pass

    _lock_fd = fd
    _lock_path = lock_file
    atexit.register(_release_scheduler_process_lock)
    return True


def init_scheduler(app: Flask) -> None:
    """Start an embedded APScheduler BackgroundScheduler with all jobs."""
    global _scheduler

    if os.getenv("LYRA_SCHEDULER_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("[scheduler] disabled via LYRA_SCHEDULER_DISABLED; skipping")
        return

    # In Flask debug mode Werkzeug spawns a reloader watcher process before
    # the actual serving child. Only start the scheduler in the serving child.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        logger.debug("[scheduler] reloader watcher process; deferring scheduler init")
        return

    if _scheduler is not None:
        logger.debug("[scheduler] already running; skipping duplicate init")
        return

    lock_acquired = False
    if _scheduler_lock_enabled():
        if not _acquire_scheduler_process_lock():
            logger.warning("[scheduler] lock held by another process; skipping embedded scheduler start")
            return
        lock_acquired = True

    try:
        from apscheduler.executors.pool import ThreadPoolExecutor as APThreadPool
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        if lock_acquired:
            _release_scheduler_process_lock()
        logger.warning(
            "[scheduler] APScheduler not installed; background jobs disabled. "
            "Run: pip install apscheduler"
        )
        return

    # Import job functions from the single source of truth.
    try:
        from oracle.worker import (
            job_acquire_drain,
            job_biographer_enrich,
            job_credits_enrich,
            job_graph_build,
            job_graph_similarity,
            job_lastfm_sync,
            job_listenbrainz_discover,
            job_structure_analyze,
            job_taste_prioritize,
        )
    except Exception as exc:  # noqa: BLE001
        if lock_acquired:
            _release_scheduler_process_lock()
        logger.error("[scheduler] could not import job functions: %s", exc, exc_info=True)
        return

    _lastfm_min = int(os.getenv("LYRA_WORKER_LASTFM_INTERVAL_MIN", "30"))
    _graph_hr = int(os.getenv("LYRA_WORKER_GRAPH_INTERVAL_HR", "6"))
    _enrich_hr = int(os.getenv("LYRA_WORKER_ENRICH_INTERVAL_HR", "24"))
    _acquire_min = int(os.getenv("LYRA_WORKER_ACQUIRE_INTERVAL_MIN", "10"))
    _prioritize_hr = int(os.getenv("LYRA_WORKER_PRIORITIZE_INTERVAL_HR", "6"))
    _lb_discover_hr = int(os.getenv("LYRA_WORKER_LB_DISCOVER_INTERVAL_HR", "24"))
    _graph_similarity_hr = int(os.getenv("LYRA_WORKER_GRAPH_SIMILARITY_INTERVAL_HR", "72"))
    _credits_hr = int(os.getenv("LYRA_WORKER_CREDITS_INTERVAL_HR", "6"))
    _structure_hr = int(os.getenv("LYRA_WORKER_STRUCTURE_INTERVAL_HR", "12"))

    scheduler = BackgroundScheduler(
        executors={"default": APThreadPool(max_workers=2)},
        timezone="UTC",
    )

    scheduler.add_job(job_lastfm_sync, "interval", minutes=_lastfm_min, id="lastfm_sync", next_run_time=None)
    scheduler.add_job(job_graph_build, "interval", hours=_graph_hr, id="graph_build", next_run_time=None)
    scheduler.add_job(job_biographer_enrich, "interval", hours=_enrich_hr, id="biographer_enrich", next_run_time=None)
    scheduler.add_job(job_acquire_drain, "interval", minutes=_acquire_min, id="acquire_drain", next_run_time=None)
    scheduler.add_job(job_taste_prioritize, "interval", hours=_prioritize_hr, id="taste_prioritize", next_run_time=None)
    scheduler.add_job(job_listenbrainz_discover, "interval", hours=_lb_discover_hr, id="listenbrainz_discover", next_run_time=None)
    scheduler.add_job(job_graph_similarity, "interval", hours=_graph_similarity_hr, id="graph_similarity", next_run_time=None)
    scheduler.add_job(job_credits_enrich, "interval", hours=_credits_hr, id="credits_enrich", next_run_time=None)
    scheduler.add_job(job_structure_analyze, "interval", hours=_structure_hr, id="structure_analyze", next_run_time=None)

    try:
        scheduler.start()
    except Exception:  # noqa: BLE001
        if lock_acquired:
            _release_scheduler_process_lock()
        raise

    _scheduler = scheduler

    logger.info(
        "[scheduler] embedded scheduler started; "
        "lastfm=%dmin graph=%dhr enrich=%dhr acquire=%dmin prioritize=%dhr "
        "listenbrainz=%dhr similarity=%dhr credits=%dhr structure=%dhr",
        _lastfm_min,
        _graph_hr,
        _enrich_hr,
        _acquire_min,
        _prioritize_hr,
        _lb_discover_hr,
        _graph_similarity_hr,
        _credits_hr,
        _structure_hr,
    )


def get_scheduler():
    """Return the running scheduler instance, or None if not started."""
    return _scheduler
