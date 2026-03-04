"""Discovery blueprint — deep cut, playlust, oracle discovery, beefweb bridge."""

from __future__ import annotations

import os
import traceback

from flask import Blueprint, jsonify, request

bp = Blueprint("discovery", __name__)


# ---------------------------------------------------------------------------
# Routes — Oracle Discovery (the CORE pipeline)
# ---------------------------------------------------------------------------

@bp.route("/api/oracle/discover", methods=["POST"])
def api_oracle_discover():
    """The Oracle discovery loop: find music you don't have based on taste,
    connections, scene, and culture.

    Pipeline:
        1. Identify user's top Spotify artists (by listening time)
        2. Traverse connections graph (member_of, collab, influence)
        3. Find connected artists NOT in the user's library
        4. Score by taste fit + connection strength
        5. Return suggestions with real cultural reasons
    """
    try:
        from oracle.discover import oracle_discover
        body = request.get_json(silent=True) or {}
        limit = int(body.get("limit", 30))
        min_connection_weight = float(body.get("min_weight", 0.3))
        seed_artist = (body.get("seed_artist") or "").strip() or None
        results = oracle_discover(
            limit=limit,
            min_connection_weight=min_connection_weight,
            seed_artist=seed_artist,
        )
        return jsonify({"count": len(results), "results": results})
    except Exception as exc:
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500


@bp.route("/api/oracle/discover/queue", methods=["POST"])
def api_oracle_discover_queue():
    """Queue oracle-discovered artists/tracks for acquisition."""
    try:
        from oracle.db.schema import get_connection
        body = request.get_json(silent=True) or {}
        tracks = body.get("tracks", [])
        if not tracks:
            return jsonify({"error": "tracks list required"}), 400
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        queued = 0
        for t in tracks:
            artist = (t.get("artist") or "").strip()
            title = (t.get("title") or "").strip()
            album = (t.get("album") or "").strip()
            if not artist:
                continue
            cursor.execute(
                "INSERT OR IGNORE INTO acquisition_queue (artist, title, album, source, status, priority_score) "
                "VALUES (?, ?, ?, 'oracle_discover', 'pending', ?)",
                (artist, title or "TBD", album, float(t.get("score", 0.5))),
            )
            queued += cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({"queued": queued, "total": len(tracks)})
    except Exception as exc:
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500


@bp.route("/api/oracle/gaps", methods=["GET"])
def api_oracle_gaps():
    """Find Spotify library tracks that were never queued for acquisition."""
    try:
        from oracle.db.schema import get_connection
        conn = get_connection(timeout=10.0)
        c = conn.cursor()
        limit = request.args.get("limit", 100, type=int)
        c.execute("""
            SELECT sl.artist, sl.title, sl.album, sl.popularity,
                   sl.release_date, sl.spotify_uri
            FROM spotify_library sl
            WHERE sl.spotify_uri NOT IN (
                SELECT COALESCE(aq.spotify_uri, '') FROM acquisition_queue aq
                WHERE aq.spotify_uri IS NOT NULL
            )
            ORDER BY sl.popularity DESC
            LIMIT ?
        """, (limit,))
        gaps = []
        for row in c.fetchall():
            gaps.append({
                "artist": row[0], "title": row[1], "album": row[2],
                "popularity": row[3], "release_date": row[4],
                "spotify_uri": row[5],
            })
        conn.close()
        return jsonify({"count": len(gaps), "results": gaps})
    except Exception as exc:
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500


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
