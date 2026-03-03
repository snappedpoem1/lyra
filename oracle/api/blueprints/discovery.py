"""Discovery blueprint — deep cut, playlust, beefweb bridge."""

from __future__ import annotations

import os
import traceback

from flask import Blueprint, jsonify, request

bp = Blueprint("discovery", __name__)


# ---------------------------------------------------------------------------
# Routes — Deep Cut
# ---------------------------------------------------------------------------

@bp.route("/api/deep-cut/hunt", methods=["POST"])
def api_deep_cut_hunt():
    """Hunt for acclaimed-but-obscure tracks in the local library."""
    try:
        from oracle.deepcut import DeepCut
        body = request.get_json(silent=True) or {}
        dc = DeepCut()
        results = dc.hunt_by_obscurity(
            genre=body.get("genre"),
            artist=body.get("artist"),
            min_obscurity=float(body.get("min_obscurity", 0.6)),
            max_obscurity=float(body.get("max_obscurity", 10.0)),
            min_acclaim=float(body.get("min_acclaim", 0.0)),
            limit=int(body.get("limit", 20)),
        )
        return jsonify({"count": len(results), "results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/deep-cut/stats", methods=["GET"])
def api_deep_cut_stats():
    """Return deep cut potential statistics for the library."""
    try:
        from oracle.deepcut import DeepCut
        return jsonify(DeepCut().get_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/deep-cut/taste", methods=["POST"])
def api_deep_cut_taste():
    """Hunt for deep cuts that align with a provided taste profile."""
    try:
        from oracle.deepcut import DeepCut
        body = request.get_json(silent=True) or {}
        taste = body.get("taste_profile", {})
        if not taste:
            return jsonify({"error": "taste_profile is required"}), 400
        results = DeepCut().hunt_with_taste_context(
            taste_profile=taste,
            limit=int(body.get("limit", 20)),
        )
        return jsonify({"count": len(results), "results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Playlust 4-Act Arc Generator
# ---------------------------------------------------------------------------

@bp.route("/api/playlust/generate", methods=["POST"])
def api_playlust_generate():
    """Generate a 4-act Playlust emotional arc playlist."""
    try:
        from oracle.playlust import Playlust
        body = request.get_json(silent=True) or {}
        pl = Playlust()
        run = pl.generate(
            mood=body.get("mood"),
            duration_minutes=int(body.get("duration_minutes", 60)),
            name=body.get("name"),
            taste_context=body.get("taste_profile"),
            use_deepcut=bool(body.get("use_deepcut", True)),
        )

        tracks = [
            {
                "rank": t.rank,
                "path": t.path,
                "artist": t.artist,
                "title": t.title,
                "score": t.global_score,
                "reasons": [r.dict() for r in t.reasons],
            }
            for t in run.tracks
        ]

        acts_map: dict = {}
        for t in tracks:
            act_reason = next((r for r in t["reasons"] if r["type"].startswith("act:")), None)
            act_key = act_reason["type"].replace("act:", "") if act_reason else "unknown"
            acts_map.setdefault(act_key, []).append(t)

        act_order = ["aggressive", "seductive", "breakdown", "sublime"]
        acts_out = [{"act": a, "tracks": acts_map.get(a, [])} for a in act_order]

        return jsonify({
            "run_uuid": run.uuid,
            "track_count": len(tracks),
            "narrative": run.prompt,
            "acts": acts_out,
            "tracks": tracks,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/playlust/acts", methods=["GET"])
def api_playlust_acts():
    """Return the four act definitions and their target dimensional profiles."""
    try:
        from oracle.playlust import Playlust
        return jsonify({"acts": Playlust().get_act_definitions()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — BeefWeb Bridge (foobar2000)
# ---------------------------------------------------------------------------

@bp.route("/api/listen/status", methods=["GET"])
def api_listen_status():
    """Check BeefWeb connectivity and return current playback state."""
    try:
        from oracle.integrations.beefweb_bridge import BeefWebBridge
        host = os.getenv("BEEFWEB_HOST", "localhost")
        port = int(os.getenv("BEEFWEB_PORT", "8880"))
        bridge = BeefWebBridge(host=host, port=port)
        connected = bridge.check_connection()
        now_playing = bridge.get_current_track() if connected else None
        return jsonify({"connected": connected, "now_playing": now_playing})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/listen/now-playing", methods=["GET"])
def api_listen_now_playing():
    """Return only the currently playing track info (lightweight poll endpoint)."""
    try:
        from oracle.integrations.beefweb_bridge import BeefWebBridge
        host = os.getenv("BEEFWEB_HOST", "localhost")
        port = int(os.getenv("BEEFWEB_PORT", "8880"))
        bridge = BeefWebBridge(host=host, port=port)
        track = bridge.get_current_track()
        if not track or track.get("state") == "stopped":
            return jsonify({"state": "stopped", "track": None})
        return jsonify({"state": track["state"], "track": track})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
