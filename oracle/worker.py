"""Lyra background worker — APScheduler process for recurring intelligence jobs.

Runs as a standalone process alongside the Flask API.
Does NOT block the API; shares the same SQLite DB via WAL mode.

Jobs:
  every 30 min  — Last.fm history sync → taste update
  every 6 hours — Incremental graph build (new connections)
  every 6 hours — Acquisition queue taste-prioritization
  every 24 hours — Biographer enrichment (first 50 stale artists)
  every 10 min  — Acquisition queue drain (5 tracks)

Env vars:
  LYRA_WORKER_LASTFM_INTERVAL_MIN   — Last.fm sync interval (default 30)
  LYRA_WORKER_GRAPH_INTERVAL_HR     — Graph build interval (default 6)
  LYRA_WORKER_ENRICH_INTERVAL_HR    — Biographer interval (default 24)
  LYRA_WORKER_ACQUIRE_INTERVAL_MIN  — Acquire drain interval (default 10)
  LYRA_WORKER_PRIORITIZE_INTERVAL_HR — Priority rescore interval (default 6)
  LYRA_WRITE_MODE                   — Must be 'apply_allowed' for writes

Usage:
  python -m oracle.worker
  oracle worker start
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load env at module import so all job functions see credentials
load_dotenv(override=False)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interval config
# ---------------------------------------------------------------------------
_LASTFM_MIN = int(os.getenv("LYRA_WORKER_LASTFM_INTERVAL_MIN", "30"))
_GRAPH_HR = int(os.getenv("LYRA_WORKER_GRAPH_INTERVAL_HR", "6"))
_ENRICH_HR = int(os.getenv("LYRA_WORKER_ENRICH_INTERVAL_HR", "24"))
_ACQUIRE_MIN = int(os.getenv("LYRA_WORKER_ACQUIRE_INTERVAL_MIN", "10"))
_PRIORITIZE_HR = int(os.getenv("LYRA_WORKER_PRIORITIZE_INTERVAL_HR", "6"))


# ---------------------------------------------------------------------------
# Job functions — each is self-contained with its own error handling
# ---------------------------------------------------------------------------

def job_lastfm_sync() -> None:
    """Pull Last.fm recent plays and push into taste_profile."""
    logger.info("[worker:lastfm] starting sync (lookback=7d)")
    try:
        from oracle.integrations.lastfm_history import sync_lastfm_to_taste
        stats = sync_lastfm_to_taste(lookback_days=7)
        if stats.get("skipped"):
            logger.info("[worker:lastfm] skipped: %s", stats.get("reason"))
        else:
            logger.info(
                "[worker:lastfm] done — fetched=%s matched=%s written=%s",
                stats.get("fetched"), stats.get("matched"), stats.get("written"),
            )
    except Exception as exc:
        logger.error("[worker:lastfm] error: %s", exc, exc_info=True)


def job_graph_build() -> None:
    """Add new connection edges to the graph (incremental, skips existing)."""
    logger.info("[worker:graph] incremental build starting")
    try:
        from oracle.graph_builder import GraphBuilder
        added = GraphBuilder().build_incremental()
        logger.info("[worker:graph] done — %d edges added", added)
    except Exception as exc:
        logger.error("[worker:graph] error: %s", exc, exc_info=True)


def job_biographer_enrich() -> None:
    """Enrich the 50 most-stale artists with biographer."""
    logger.info("[worker:biographer] enriching up to 50 stale artists")
    try:
        from oracle.enrichers.biographer import Biographer
        stats = Biographer().enrich_stale_artists(limit=50)
        logger.info(
            "[worker:biographer] done — processed=%s failed=%s",
            stats.get("processed"), stats.get("failed"),
        )
    except Exception as exc:
        logger.error("[worker:biographer] error: %s", exc, exc_info=True)


def job_acquire_drain() -> None:
    """Pull the next 5 highest-priority pending items from acquisition queue."""
    logger.info("[worker:acquire] draining 5 queue items")
    try:
        from oracle.acquirers.taste_prioritizer import get_next_priority_batch
        from oracle.acquirers.waterfall import AcquisitionWaterfall
        from oracle.db.schema import get_connection, get_write_mode

        if get_write_mode() != "apply_allowed":
            logger.info("[worker:acquire] write mode blocked, skipping drain")
            return

        items = get_next_priority_batch(limit=5)
        if not items:
            logger.info("[worker:acquire] queue empty or fully processed")
            return

        waterfall = AcquisitionWaterfall()
        conn = get_connection(timeout=10.0)

        for item in items:
            queue_id, artist, title = item["id"], item["artist"], item["title"]
            try:
                conn.execute(
                    "UPDATE acquisition_queue SET status='processing' WHERE id=?",
                    (queue_id,)
                )
                conn.commit()

                result = waterfall.acquire(artist=artist, title=title)
                status = "completed" if result.success else "failed"
                error = result.error if not result.success else None

                conn.execute(
                    "UPDATE acquisition_queue SET status=?, error=? WHERE id=?",
                    (status, error, queue_id)
                )
                conn.commit()
                logger.info(
                    "[worker:acquire] %s '%s - %s' via tier %s",
                    "✓" if result.success else "✗", artist, title, result.tier
                )
            except Exception as exc:
                logger.error("[worker:acquire] item %s failed: %s", queue_id, exc)
                try:
                    conn.execute(
                        "UPDATE acquisition_queue SET status='failed', error=? WHERE id=?",
                        (str(exc), queue_id)
                    )
                    conn.commit()
                except Exception:
                    pass

        conn.close()
    except Exception as exc:
        logger.error("[worker:acquire] drain error: %s", exc, exc_info=True)


def job_taste_prioritize() -> None:
    """Re-score acquisition queue items by taste alignment."""
    logger.info("[worker:prioritize] rescoring acquisition queue")
    try:
        from oracle.acquirers.taste_prioritizer import prioritize_queue
        stats = prioritize_queue()
        logger.info(
            "[worker:prioritize] done — updated=%s skipped=%s",
            stats.get("updated"), stats.get("skipped"),
        )
    except Exception as exc:
        logger.error("[worker:prioritize] error: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def build_scheduler():
    """Build and return a configured APScheduler BlockingScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor as APThreadPool
    except ImportError:
        logger.error(
            "[worker] APScheduler not installed. Run: pip install apscheduler"
        )
        sys.exit(1)

    executors = {"default": APThreadPool(max_workers=2)}
    scheduler = BlockingScheduler(executors=executors, timezone="UTC")

    scheduler.add_job(
        job_lastfm_sync,
        "interval",
        minutes=_LASTFM_MIN,
        id="lastfm_sync",
        next_run_time=None,  # don't run immediately on start
    )
    scheduler.add_job(
        job_graph_build,
        "interval",
        hours=_GRAPH_HR,
        id="graph_build",
        next_run_time=None,
    )
    scheduler.add_job(
        job_biographer_enrich,
        "interval",
        hours=_ENRICH_HR,
        id="biographer_enrich",
        next_run_time=None,
    )
    scheduler.add_job(
        job_acquire_drain,
        "interval",
        minutes=_ACQUIRE_MIN,
        id="acquire_drain",
        next_run_time=None,
    )
    scheduler.add_job(
        job_taste_prioritize,
        "interval",
        hours=_PRIORITIZE_HR,
        id="taste_prioritize",
        next_run_time=None,
    )

    return scheduler


def run_all_once() -> None:
    """Run every job immediately once, sequentially. Useful for testing."""
    logger.info("[worker] running all jobs once")
    job_lastfm_sync()
    job_taste_prioritize()
    job_graph_build()
    job_biographer_enrich()
    logger.info("[worker] all jobs complete")


def start() -> None:
    """Start the worker scheduler — blocks until SIGINT/SIGTERM."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Point HuggingFace cache at project root
    project_root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("HF_HOME", str(project_root / "hf_cache"))

    scheduler = build_scheduler()

    def _shutdown(signum, frame):
        logger.info("[worker] shutdown signal received — stopping scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("[worker] Lyra background worker starting")
    logger.info("[worker] Jobs: lastfm=%dmin  graph=%dhr  enrich=%dhr  acquire=%dmin  prioritize=%dhr",
                _LASTFM_MIN, _GRAPH_HR, _ENRICH_HR, _ACQUIRE_MIN, _PRIORITIZE_HR)

    # Run taste prioritize immediately on startup so queue is ordered
    try:
        job_taste_prioritize()
    except Exception as exc:
        logger.warning("[worker] startup prioritize failed: %s", exc)

    scheduler.start()


# ---------------------------------------------------------------------------
# CLI entrypoint: python -m oracle.worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lyra background worker")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("start", help="Start the background worker scheduler")
    sub.add_parser("run-once", help="Run all jobs once and exit")

    args = parser.parse_args()

    if args.cmd == "run-once":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        run_all_once()
    else:
        start()
