"""Ingest confidence API blueprint.

Exposes lifecycle state machine data per SPEC-007.

Routes:
    GET /api/ingest/confidence/summary  — aggregate counts + stall count
    GET /api/ingest/confidence/recent   — latest N transitions (default 20)
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from oracle.ingest_confidence import get_confidence_summary, get_recent_transitions

logger = logging.getLogger(__name__)

bp = Blueprint("ingest", __name__)


@bp.route("/api/ingest/confidence/summary")
def confidence_summary() -> tuple:
    """Return aggregate ingest confidence state counts.

    Returns:
        JSON with summary dict, stalled count, total_unique_filepaths,
        and backfill_count.
    """
    try:
        return jsonify(get_confidence_summary()), 200
    except Exception:
        logger.exception("Failed to load ingest confidence summary")
        return jsonify({"error": "internal_error"}), 500


@bp.route("/api/ingest/confidence/recent")
def confidence_recent() -> tuple:
    """Return the most recent ingest confidence transitions.

    Query params:
        limit (int): Maximum rows to return, capped at 200. Default 20.

    Returns:
        JSON with ``transitions`` list.
    """
    try:
        raw_limit = request.args.get("limit", "20")
        limit = min(int(raw_limit), 200)
    except (TypeError, ValueError):
        limit = 20
    try:
        return jsonify({"transitions": get_recent_transitions(limit=limit)}), 200
    except Exception:
        logger.exception("Failed to load ingest confidence transitions")
        return jsonify({"error": "internal_error"}), 500
