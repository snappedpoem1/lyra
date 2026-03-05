"""Scheduler rib — embedded APScheduler running inside the Flask process.

This replaces the requirement to run ``oracle worker start`` as a separate
process.  Jobs run in daemon threads attached to the same process as the API,
sharing memory and requiring no inter-process coordination.

Design notes
------------
* Uses ``BackgroundScheduler`` (non-blocking) — Flask's own thread handles
  HTTP; the scheduler gets a small ThreadPool alongside it.
* Job functions are imported directly from ``oracle.worker`` — single source
  of truth for job logic, no duplication.
* Protected against Werkzeug debug-mode double-start: the scheduler is only
  started in the *serving* process, not the reloader watcher.
* All jobs default to ``next_run_time=None`` so the first execution is
  deferred to the first scheduled interval (no burst on API boot).
* ``LYRA_SCHEDULER_DISABLED=1`` lets CI / tests skip the scheduler entirely.

Interval env vars (same as oracle/worker.py):
  LYRA_WORKER_LASTFM_INTERVAL_MIN
  LYRA_WORKER_GRAPH_INTERVAL_HR
  LYRA_WORKER_ENRICH_INTERVAL_HR
  LYRA_WORKER_ACQUIRE_INTERVAL_MIN
  LYRA_WORKER_PRIORITIZE_INTERVAL_HR
"""

from __future__ import annotations

import logging
import os

from flask import Flask

logger = logging.getLogger(__name__)

_scheduler = None  # module-level singleton guard


def init_scheduler(app: Flask) -> None:
    """Start an embedded APScheduler ``BackgroundScheduler`` with all jobs.

    Safe to call multiple times — only the first call creates the scheduler.
    No-ops when:
      * ``LYRA_SCHEDULER_DISABLED=1`` is set
      * Running inside the Werkzeug reloader watcher process
      * APScheduler is not installed (logs a warning, continues gracefully)

    Args:
        app: The Flask application instance (used for debug flag check).
    """
    global _scheduler

    if os.getenv("LYRA_SCHEDULER_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("[scheduler] disabled via LYRA_SCHEDULER_DISABLED — skipping")
        return

    # In Flask debug mode Werkzeug spawns a reloader watcher process before
    # the actual serving child.  Only start the scheduler in the serving child.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        logger.debug("[scheduler] reloader watcher process — deferring scheduler init")
        return

    if _scheduler is not None:
        logger.debug("[scheduler] already running — skipping duplicate init")
        return

    try:
        from apscheduler.executors.pool import ThreadPoolExecutor as APThreadPool
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "[scheduler] APScheduler not installed — background jobs disabled. "
            "Run: pip install apscheduler"
        )
        return

    # Import job functions from the single source of truth.
    try:
        from oracle.worker import (
            job_acquire_drain,
            job_biographer_enrich,
            job_graph_build,
            job_graph_similarity,
            job_lastfm_sync,
            job_listenbrainz_discover,
            job_taste_prioritize,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[scheduler] could not import job functions: %s", exc, exc_info=True)
        return

    _lastfm_min = int(os.getenv("LYRA_WORKER_LASTFM_INTERVAL_MIN", "30"))
    _graph_hr = int(os.getenv("LYRA_WORKER_GRAPH_INTERVAL_HR", "6"))
    _enrich_hr = int(os.getenv("LYRA_WORKER_ENRICH_INTERVAL_HR", "24"))
    _acquire_min = int(os.getenv("LYRA_WORKER_ACQUIRE_INTERVAL_MIN", "10"))
    _prioritize_hr = int(os.getenv("LYRA_WORKER_PRIORITIZE_INTERVAL_HR", "6"))
    _lb_discover_hr = int(os.getenv("LYRA_WORKER_LB_DISCOVER_INTERVAL_HR", "24"))
    _graph_similarity_hr = int(os.getenv("LYRA_WORKER_GRAPH_SIMILARITY_INTERVAL_HR", "72"))

    scheduler = BackgroundScheduler(
        executors={"default": APThreadPool(max_workers=2)},
        timezone="UTC",
    )

    scheduler.add_job(job_lastfm_sync,          "interval", minutes=_lastfm_min,        id="lastfm_sync",         next_run_time=None)
    scheduler.add_job(job_graph_build,           "interval", hours=_graph_hr,            id="graph_build",         next_run_time=None)
    scheduler.add_job(job_biographer_enrich,     "interval", hours=_enrich_hr,           id="biographer_enrich",   next_run_time=None)
    scheduler.add_job(job_acquire_drain,         "interval", minutes=_acquire_min,       id="acquire_drain",       next_run_time=None)
    scheduler.add_job(job_taste_prioritize,      "interval", hours=_prioritize_hr,       id="taste_prioritize",    next_run_time=None)
    scheduler.add_job(job_listenbrainz_discover, "interval", hours=_lb_discover_hr,      id="listenbrainz_discover",next_run_time=None)
    scheduler.add_job(job_graph_similarity,      "interval", hours=_graph_similarity_hr, id="graph_similarity",    next_run_time=None)

    scheduler.start()
    _scheduler = scheduler

    logger.info(
        "[scheduler] embedded scheduler started — "
        "lastfm=%dmin  graph=%dhr  enrich=%dhr  acquire=%dmin  prioritize=%dhr  "
        "listenbrainz=%dhr  similarity=%dhr",
        _lastfm_min, _graph_hr, _enrich_hr, _acquire_min, _prioritize_hr,
        _lb_discover_hr, _graph_similarity_hr,
    )


def get_scheduler():
    """Return the running scheduler instance, or ``None`` if not started.

    Useful for introspection endpoints that want to surface job next-run times.
    """
    return _scheduler
