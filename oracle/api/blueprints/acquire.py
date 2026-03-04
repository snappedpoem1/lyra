"""Acquisition blueprint — YouTube, batch, downloads, Spotify imports."""

from __future__ import annotations

import json
import os
import queue as _queue
import sqlite3
import threading
import time as _time
import traceback
import uuid as _uuid
from pathlib import Path
from typing import Dict, List

from flask import Blueprint, Response, jsonify, request

from oracle.api.helpers import _json_safe
from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection
from oracle.validation import sanitize_integer, validate_boolean, validate_url

bp = Blueprint("acquire", __name__)

# ---------------------------------------------------------------------------
# In-process batch job state  (module-level — lives for the server's lifetime)
# ---------------------------------------------------------------------------

_batch_jobs: Dict[str, dict] = {}
_batch_queues: Dict[str, _queue.Queue] = {}


def _run_batch_job(job_id: str, queries: List[str], workers: int, run_pipeline: bool) -> None:
    """Background thread: runs fast_batch and pushes SSE events."""
    from oracle.fast_batch import _download_one, FAST_SLEEP_MIN, FAST_SLEEP_MAX
    from oracle.config import load_config
    from concurrent.futures import ThreadPoolExecutor, as_completed

    eq = _batch_queues[job_id]
    job = _batch_jobs[job_id]

    cfg = load_config()
    cfg.sleep_min = FAST_SLEEP_MIN
    cfg.sleep_max = FAST_SLEEP_MAX
    db_path = Path(os.getenv("LYRA_DB_PATH", "lyra_registry.db"))

    total = len(queries)
    job["total"] = total
    eq.put({"event": "start", "total": total, "workers": workers})

    ok = 0
    fail = 0
    results: list = []
    t0 = _time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_one, q.strip(), cfg, db_path, i, total): (i, q)
            for i, q in enumerate(queries, 1)
            if q.strip()
        }
        for future in as_completed(futures):
            idx, query = futures[future]
            r = future.result()
            results.append(r)
            if r["success"]:
                ok += 1
                eq.put({
                    "event": "downloaded", "idx": idx, "query": query,
                    "artist": r.get("artist", ""), "title": r.get("title", ""),
                    "elapsed": round(r.get("elapsed", 0), 1),
                    "ok": ok, "fail": fail, "total": total,
                })
            else:
                fail += 1
                eq.put({
                    "event": "failed", "idx": idx, "query": query,
                    "error": r.get("error", ""),
                    "ok": ok, "fail": fail, "total": total,
                })

    dl_time = round(_time.perf_counter() - t0, 1)
    eq.put({"event": "downloads_done", "ok": ok, "fail": fail, "time": dl_time})
    job["download_results"] = results

    if run_pipeline and ok > 0:
        downloads_path = str(cfg.download_dir.resolve())

        eq.put({"event": "pipeline", "stage": "scan"})
        t1 = _time.perf_counter()
        from oracle.scanner import scan_library as _scan
        scan_r = _scan(downloads_path)
        eq.put({"event": "pipeline_done", "stage": "scan", "result": scan_r,
                "time": round(_time.perf_counter() - t1, 2)})

        eq.put({"event": "pipeline", "stage": "index"})
        t1 = _time.perf_counter()
        from oracle.indexer import index_library as _index
        idx_r = _index(library_path=downloads_path)
        eq.put({"event": "pipeline_done", "stage": "index", "result": idx_r,
                "time": round(_time.perf_counter() - t1, 2)})

        eq.put({"event": "pipeline", "stage": "score"})
        t1 = _time.perf_counter()
        from oracle.scorer import score_all as _score
        score_r = _score(force=False)
        eq.put({"event": "pipeline_done", "stage": "score", "result": score_r,
                "time": round(_time.perf_counter() - t1, 2)})

    total_time = round(_time.perf_counter() - t0, 1)
    job["status"] = "complete"
    job["ok"] = ok
    job["fail"] = fail
    job["total_time"] = total_time
    eq.put({"event": "complete", "ok": ok, "fail": fail, "total_time": total_time})
    eq.put(None)  # sentinel


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/api/acquire/youtube", methods=["POST"])
def api_acquire_youtube():
    """Download from YouTube."""
    try:
        from oracle.acquirers.ytdlp import YTDLPAcquirer
        data = request.get_json() or {}
        url = data.get("url", "")
        valid, error = validate_url(url)
        if not valid:
            return jsonify({"error": error}), 400
        acquirer = YTDLPAcquirer()
        result = acquirer.download(url.strip())
        return jsonify({"result": _json_safe(result or "Download failed")})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/acquire/queue", methods=["GET"])
def api_acquire_queue():
    """Get acquisition queue."""
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, url, source, status, added_at, error
            FROM acquisition_queue
            ORDER BY added_at DESC
            LIMIT 50
            """
        )
        rows = cursor.fetchall()
        conn.close()
        queue = [
            {"id": r[0], "url": r[1], "source": r[2], "status": r[3], "added_at": r[4], "error": r[5]}
            for r in rows
        ]
        return jsonify({"queue": queue, "count": len(queue)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/acquire/process", methods=["POST"])
def api_acquire_process():
    """Process acquisition queue."""
    try:
        from oracle.acquisition import process_queue
        data = request.get_json(silent=True) or {}
        limit = sanitize_integer(data.get("limit", 0), default=0, min_val=0, max_val=1000)
        results = process_queue(limit=limit)
        return jsonify(results)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return jsonify({"error": "database is locked; retry shortly"}), 503
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/acquire/batch", methods=["POST"])
def api_acquire_batch():
    """Start a parallel batch download job. Returns job_id for SSE streaming."""
    try:
        data = request.get_json() or {}
        raw = data.get("queries", "")
        workers = min(int(data.get("workers", 4)), 8)
        run_pipeline = data.get("pipeline", True)

        if isinstance(raw, str):
            queries = [q.strip() for q in raw.splitlines() if q.strip() and not q.strip().startswith("#")]
        elif isinstance(raw, list):
            queries = [q.strip() for q in raw if q.strip()]
        else:
            return jsonify({"error": "queries must be string or list"}), 400

        if not queries:
            return jsonify({"error": "No queries provided"}), 400
        if len(queries) > 200:
            return jsonify({"error": f"Max 200 queries per batch, got {len(queries)}"}), 400

        job_id = _uuid.uuid4().hex[:12]
        _batch_jobs[job_id] = {"status": "running", "total": len(queries)}
        _batch_queues[job_id] = _queue.Queue()

        t = threading.Thread(
            target=_run_batch_job,
            args=(job_id, queries, workers, run_pipeline),
            daemon=True,
        )
        t.start()
        return jsonify({"job_id": job_id, "total": len(queries), "workers": workers})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/acquire/batch/<job_id>/stream")
def api_acquire_batch_stream(job_id: str):
    """SSE stream for batch job progress."""
    if job_id not in _batch_queues:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        eq = _batch_queues[job_id]
        while True:
            try:
                msg = eq.get(timeout=120)
                if msg is None:
                    yield f"data: {json.dumps({'event': 'done'})}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except _queue.Empty:
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/acquire/batch/<job_id>/status")
def api_acquire_batch_status(job_id: str):
    """Get batch job status (polling fallback)."""
    job = _batch_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@bp.route("/api/downloads", methods=["GET"])
def api_downloads_list():
    """List downloads folder."""
    try:
        from oracle.download_processor import list_downloads
        show_metadata = request.args.get("metadata", "false").lower() == "true"
        downloads = list_downloads(show_metadata=show_metadata)
        return jsonify({"downloads": downloads, "count": len(downloads)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/downloads/organize", methods=["POST"])
def api_downloads_organize():
    """Organize downloads into library."""
    try:
        from oracle.acquirers.guarded_import import process_downloads
        data = request.get_json() or {}
        results = process_downloads(
            target_library=data.get("library") or str(LIBRARY_BASE),
            clean_names=data.get("clean_names", True),
            dry_run=data.get("dry_run", False),
            scan_after=data.get("scan_after", True),
        )
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/spotify/missing", methods=["GET"])
def api_spotify_missing():
    """Find Spotify favourites not in local library — acquisition candidates."""
    try:
        min_plays = sanitize_integer(request.args.get("min_plays", 5), default=5, min_val=0, max_val=1000000)
        limit = sanitize_integer(request.args.get("limit", 100), default=100, min_val=1, max_val=1000)

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT artist, title, album, spotify_uri, source, play_count, priority_score, status, added_at
            FROM acquisition_queue
            WHERE source IN ('history', 'liked', 'playlist', 'top_tracks')
              AND status = 'pending'
              AND COALESCE(play_count, 0) >= ?
            ORDER BY COALESCE(priority_score, 0.0) DESC, COALESCE(play_count, 0) DESC, added_at DESC
            LIMIT ?
            """,
            (min_plays, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        missing = [
            {
                "artist": r[0], "title": r[1], "album": r[2], "spotify_uri": r[3],
                "source": r[4], "play_count": r[5], "priority_score": r[6],
                "status": r[7], "added_at": r[8],
            }
            for r in rows
        ]
        return jsonify({"ok": True, "missing": missing, "count": len(missing), "min_plays": min_plays})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/spotify/stats", methods=["GET"])
def api_spotify_stats():
    """Spotify import statistics."""
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        stats: dict = {}

        for table in ("spotify_history", "spotify_library", "spotify_features"):
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,))
            exists = cursor.fetchone()[0] > 0
            stats[f"{table}_count"] = int(cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if exists else 0

        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
            FROM acquisition_queue
            WHERE source IN ('history', 'liked', 'playlist', 'top_tracks')
            """
        )
        pending, completed, failed = cursor.fetchone()
        stats["queue_pending"] = int(pending or 0)
        stats["queue_completed"] = int(completed or 0)
        stats["queue_failed"] = int(failed or 0)

        cursor.execute(
            """
            SELECT artist, COUNT(*) AS play_count, SUM(COALESCE(ms_played, 0)) AS total_ms
            FROM spotify_history
            WHERE artist IS NOT NULL AND trim(artist) != ''
            GROUP BY artist
            ORDER BY play_count DESC, total_ms DESC
            LIMIT 25
            """
        )
        stats["top_artists"] = [
            {"name": r[0], "score": int(r[1] or 0), "plays": int(r[1] or 0), "total_ms": int(r[2] or 0)}
            for r in cursor.fetchall()
        ]

        conn.close()
        return jsonify({"ok": True, **stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
