"""Radio, playback, and taste blueprint."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

from oracle.db.schema import get_connection
from oracle.validation import validate_boolean

bp = Blueprint("radio", __name__)

# ---------------------------------------------------------------------------
# Lazy engine import
# ---------------------------------------------------------------------------

try:
    from oracle.radio import Radio
    _radio_engine = Radio()
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
        count = int(data.get("count", 1))
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
        count = int(data.get("count", 1))

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
    """Get discovery mode track recommendations (library edges + Last.fm)."""
    if _radio_engine is None:
        return jsonify({"error": "Radio engine not available — check server logs"}), 503
    try:
        count = request.args.get("count", 10, type=int)
        include_external = request.args.get("external", "true", type=str).lower() != "false"

        # Library edges (unplayed tracks with taste filtering)
        library_results = _radio_engine.get_discovery_track(count=count)

        # External discovery (Last.fm similar tracks not in library)
        external_results = []
        if include_external:
            try:
                external_results = _radio_engine.get_lastfm_discovery(count=count)
            except Exception as exc:
                external_results = [{"error": str(exc)}]

        return jsonify({
            "library": library_results,
            "library_count": len(library_results),
            "external": external_results,
            "external_count": len(external_results),
        })
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
        length = int(data.get("length", 20))
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
    """Seed taste profile from library averages or Spotify history."""
    try:
        from oracle.taste import seed_taste_from_library, seed_taste_from_spotify
        data = request.get_json(silent=True) or {}
        overwrite = bool(data.get("overwrite", False))
        source = (data.get("source") or "auto").strip().lower()

        # Auto mode: try Spotify first (richer signal), fall back to library
        if source == "spotify":
            result = seed_taste_from_spotify(overwrite_existing=overwrite)
        elif source == "library":
            result = seed_taste_from_library(overwrite_existing=overwrite)
        else:
            # Auto: try spotify, fall back to library
            result = seed_taste_from_spotify(overwrite_existing=overwrite)
            if not result.get("seeded"):
                result = seed_taste_from_library(overwrite_existing=overwrite)
                result["auto_fallback"] = "library"
            else:
                result["auto_source"] = "spotify"
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
