"""Horizon intelligence API endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from oracle.horizon.prowlarr_releases import (
    get_indexer_health,
    get_upcoming_releases,
    search_releases,
)

logger = logging.getLogger(__name__)

bp = Blueprint("horizon", __name__, url_prefix="/api/horizon")


@bp.route("/search", methods=["GET"])
def api_search_releases() -> tuple[Any, int]:
    """Search for releases across prowlarr indexers."""
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 50))
    
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    
    try:
        results = search_releases(query, limit=limit)
        return jsonify({
            "ok": True,
            "query": query,
            "count": len(results),
            "releases": results,
        }), 200
    except Exception as exc:
        logger.exception("Horizon search failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/upcoming", methods=["GET"])
def api_get_upcoming_releases() -> tuple[Any, int]:
    """Get upcoming releases from prowlarr for monitoring."""
    artist_filter = request.args.get("artist")
    days_ahead = int(request.args.get("days", 30))
    
    try:
        results = get_upcoming_releases(artist_filter=artist_filter, days_ahead=days_ahead)
        return jsonify({
            "ok": True,
            "days_ahead": days_ahead,
            "count": len(results),
            "releases": results,
        }), 200
    except Exception as exc:
        logger.exception("Get upcoming releases failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/indexers", methods=["GET"])
def api_get_indexer_health() -> tuple[Any, int]:
    """Get health status of configured prowlarr indexers."""
    try:
        health = get_indexer_health()
        return jsonify({
            "ok": True,
            "count": len(health),
            "indexers": health,
        }), 200
    except Exception as exc:
        logger.exception("Get indexer health failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
