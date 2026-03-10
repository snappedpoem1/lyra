"""Pipeline blueprint — scan/index/score job management."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

bp = Blueprint("pipeline", __name__)

# ---------------------------------------------------------------------------
# Lazy engine import
# ---------------------------------------------------------------------------

try:
    from oracle.pipeline import get_pipeline
except Exception:
    get_pipeline = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/api/pipeline/start", methods=["POST"])
def api_pipeline_start():
    """Start an acquisition pipeline job."""
    if get_pipeline is None:
        return jsonify({"error": "Pipeline engine not available — check server logs"}), 503
    try:
        data = request.get_json() or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400
        pipeline = get_pipeline()
        job_id = pipeline.create_job(query)
        job = pipeline.get_job(job_id)
        return jsonify({"success": True, "job_id": job_id, "job": job})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/pipeline/status/<job_id>", methods=["GET"])
def api_pipeline_status(job_id: str):
    """Get pipeline job status."""
    if get_pipeline is None:
        return jsonify({"error": "Pipeline engine not available — check server logs"}), 503
    try:
        pipeline = get_pipeline()
        job = pipeline.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"success": True, "job": job})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/pipeline/run/<job_id>", methods=["POST"])
def api_pipeline_run(job_id: str):
    """Execute pipeline for a specific job."""
    try:
        from oracle.pipeline import run_pipeline
        job = run_pipeline(job_id)
        return jsonify({"success": True, "job": job})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/pipeline/jobs", methods=["GET"])
def api_pipeline_jobs():
    """List recent pipeline jobs."""
    if get_pipeline is None:
        return jsonify({"error": "Pipeline engine not available — check server logs"}), 503
    try:
        from oracle.validation import sanitize_integer
        limit = sanitize_integer(request.args.get("limit", 20), default=20, min_val=1, max_val=500)
        pipeline = get_pipeline()
        jobs = pipeline.list_jobs(limit)
        return jsonify({"success": True, "count": len(jobs), "jobs": jobs})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
