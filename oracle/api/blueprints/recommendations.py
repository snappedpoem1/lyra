"""Recommendation broker blueprint."""

from __future__ import annotations

import traceback
from typing import Any

from flask import Blueprint, jsonify, request

from oracle.provider_health import get_all_health
from oracle.recommendation_broker import record_feedback, recommend_tracks
from oracle.validation import sanitize_integer

bp = Blueprint("recommendations", __name__)


@bp.route("/api/recommendations/oracle", methods=["POST"])
def api_recommendations_oracle() -> Any:
    """Return brokered recommendations with provenance and acquisition leads."""
    try:
        data = request.get_json(silent=True) or {}
        provider_weights = data.get("provider_weights")
        if not isinstance(provider_weights, dict):
            provider_weights = None

        payload = recommend_tracks(
            seed_track_id=str(data.get("seed_track_id") or "").strip() or None,
            mode=str(data.get("mode") or "flow"),
            novelty_band=str(data.get("novelty_band") or "stretch"),
            limit=sanitize_integer(data.get("limit", 12), default=12, min_val=1, max_val=24),
            provider_weights=provider_weights,
        )
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500


@bp.route("/api/recommendations/oracle/feedback", methods=["POST"])
def api_recommendations_oracle_feedback() -> Any:
    """Persist a broker feedback event for future recommendation ranking."""
    try:
        data = request.get_json(silent=True) or {}
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = None

        payload = record_feedback(
            feedback_type=data.get("feedback_type"),
            track_id=str(data.get("track_id") or "").strip() or None,
            artist=str(data.get("artist") or "").strip() or None,
            title=str(data.get("title") or "").strip() or None,
            seed_track_id=str(data.get("seed_track_id") or "").strip() or None,
            mode=data.get("mode"),
            novelty_band=data.get("novelty_band"),
            provider=data.get("provider"),
            metadata=metadata,
        )
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500


@bp.route("/api/recommendations/providers/health", methods=["GET"])
def api_provider_health() -> Any:
    """Return provider health summaries per SPEC-006."""
    return jsonify({"providers": get_all_health()})
