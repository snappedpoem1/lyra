"""Radio, playback, and taste blueprint."""

from __future__ import annotations

import logging
import traceback

from flask import Blueprint, jsonify, request

from oracle.db.schema import get_connection
from oracle.validation import sanitize_integer

bp = Blueprint("radio", __name__)

# ---------------------------------------------------------------------------
# Lazy engine import
# ---------------------------------------------------------------------------

try:
    from oracle.radio import Radio as _RadioEngine
except Exception:
    _RadioEngine = None  # type: ignore[assignment]

try:
    _radio_engine = _RadioEngine() if _RadioEngine is not None else None
except Exception:
    _radio_engine = None


# ---------------------------------------------------------------------------
# Routes — Radio
# ---------------------------------------------------------------------------

@bp.route("/api/radio/chaos", methods=["POST"])
def api_radio_chaos():
    """Get chaos mode track recommendations."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available — check server logs"}), 503
    try:
        data = request.get_json() or {}
        track_id = (data.get("track_id") or "").strip() or None
        count = sanitize_integer(data.get("count", 1), default=1, min_val=1, max_val=100)
        results = _radio_engine.get_chaos_track(track_id, count=count)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/radio/flow", methods=["POST"])
def api_radio_flow():
    """Get flow mode track recommendations."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available — check server logs"}), 503
    try:
        data = request.get_json() or {}
        track_id = (data.get("track_id") or data.get("seed_track") or "").strip()
        count = sanitize_integer(data.get("count", 1), default=1, min_val=1, max_val=100)

        if not track_id:
            conn = get_connection(timeout=5.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT track_id FROM tracks WHERE status = 'active' "
                "ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                track_id = row[0]
            else:
                return jsonify({"error": "track_id required for flow mode (no active library tracks)"}), 400

        results = _radio_engine.get_flow_track(track_id, count=count)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/radio/discovery", methods=["GET"])
def api_radio_discovery():
    """Get discovery mode track recommendations."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available — check server logs"}), 503
    try:
        count = sanitize_integer(request.args.get("count", 1), default=1, min_val=1, max_val=100)
        results = _radio_engine.get_discovery_track(count=count)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/radio/queue", methods=["POST"])
def api_radio_queue():
    """Build a full radio queue."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available"}), 503
    try:
        data = request.get_json() or {}
        mode = (data.get("mode") or "chaos").strip()
        seed_track = (data.get("seed_track") or "").strip() or None
        length = sanitize_integer(data.get("length", 20), default=20, min_val=1, max_val=200)
        queue = _radio_engine.build_queue(mode=mode, seed_track=seed_track, length=length)
        return jsonify({"queue": queue, "count": len(queue), "mode": mode})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Playback
# ---------------------------------------------------------------------------

@bp.route("/api/playback/record", methods=["POST"])
def api_playback_record():
    """Record a playback event for taste learning."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available; check server logs"}), 503
    try:
        data = request.get_json() or {}
        track_id = (data.get("track_id") or "").strip()
        context = (data.get("context") or "manual").strip()
        skipped = bool(data.get("skipped", False))
        rating = data.get("rating")

        if not track_id:
            return jsonify({"error": "track_id is required"}), 400
        try:
            completion_rate = float(data.get("completion_rate", 1.0))
        except (TypeError, ValueError):
            return jsonify({"error": "completion_rate must be a number"}), 400
        if not (0.0 <= completion_rate <= 1.0):
            return jsonify({"error": "completion_rate must be between 0.0 and 1.0"}), 400
        if rating is not None:
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                return jsonify({"error": "rating must be an integer 1–5"}), 400
            if not (1 <= rating <= 5):
                return jsonify({"error": "rating must be an integer 1–5"}), 400

        try:
            _radio_engine.record_playback(
                track_id=track_id, context=context,
                skipped=skipped, completion_rate=completion_rate, rating=rating,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Taste
# ---------------------------------------------------------------------------

@bp.route("/api/taste/profile", methods=["GET"])
def api_taste_profile():
    """Return the user's current taste profile with library context."""
    try:
        from oracle.taste import get_taste_profile
        return jsonify(get_taste_profile())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/taste/seed", methods=["POST"])
def api_taste_seed():
    """Seed taste profile from library averages (cold-start bootstrap)."""
    try:
        from oracle.taste import seed_taste_from_library
        data = request.get_json(silent=True) or {}
        overwrite = bool(data.get("overwrite", False))
        result = seed_taste_from_library(overwrite_existing=overwrite)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/taste/backfill", methods=["POST"])
def api_taste_backfill():
    """Backfill taste profile from Spotify extended streaming history."""
    try:
        from oracle.taste_backfill import backfill_taste_from_spotify_history
        data = request.get_json(silent=True) or {}
        result = backfill_taste_from_spotify_history(
            min_ms_played=int(data.get("min_ms_played", 30000)),
            dry_run=bool(data.get("dry_run", False)),
        )
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
