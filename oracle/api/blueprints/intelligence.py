"""Intelligence blueprint — scout, lore, dna, hunter, architect."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

from oracle.api.helpers import _json_safe, _load_track, _track_row_to_dict
from oracle.db.schema import get_connection
from oracle.validation import sanitize_integer

bp = Blueprint("intelligence", __name__)

# ---------------------------------------------------------------------------
# Lazy engine imports (optional dependencies — engines may not be installed)
# ---------------------------------------------------------------------------

try:
    from oracle.scout import Scout
    _scout_engine = Scout()
except Exception:
    _scout_engine = None

try:
    from oracle.lore import Lore
    _lore_engine = Lore()
except Exception:
    _lore_engine = None

try:
    from oracle.dna import DNA
    _dna_engine = DNA()
except Exception:
    _dna_engine = None

try:
    from oracle.hunter import Hunter
    _hunter_engine = Hunter()
except Exception:
    _hunter_engine = None

try:
    from oracle.architect import Architect
    _architect_engine = Architect()
except Exception:
    _architect_engine = None


# ---------------------------------------------------------------------------
# Routes — Scout (cross-genre discovery)
# ---------------------------------------------------------------------------

@bp.route("/api/scout/cross-genre", methods=["POST"])
def api_scout_cross_genre():
    """Find sonically similar tracks across genre boundaries."""
    if _scout_engine is None:
        return jsonify({"error": "Scout engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        source_genre = (data.get("source_genre") or data.get("track_id") or "").strip()
        target_genre = (data.get("target_genre") or "").strip()
        if not source_genre:
            return jsonify({"error": "source_genre required"}), 400
        if not target_genre:
            return jsonify({"error": "target_genre required"}), 400
        n = sanitize_integer(data.get("n", 10), default=10, min_val=1, max_val=100)
        results = _scout_engine.cross_genre_hunt(source_genre, target_genre, limit=n)
        return jsonify({"results": [_json_safe(r) for r in (results or [])], "count": len(results or [])})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Lore (influence tracing)
# ---------------------------------------------------------------------------

@bp.route("/api/lore/trace", methods=["POST"])
def api_lore_trace():
    """Trace musical influences for an artist."""
    if _lore_engine is None:
        return jsonify({"error": "Lore engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        artist = data.get("artist", "")
        if not artist:
            return jsonify({"error": "artist required"}), 400
        depth = sanitize_integer(data.get("depth", 2), default=2, min_val=1, max_val=5)
        result = _lore_engine.trace_lineage(artist, depth=depth)
        return jsonify({"result": _json_safe(result)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/lore/connections", methods=["POST"])
def api_lore_connections():
    """Find connections between two artists."""
    if _lore_engine is None:
        return jsonify({"error": "Lore engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        artist_a = data.get("artist_a", "")
        artist_b = data.get("artist_b", "")
        if not artist_a or not artist_b:
            return jsonify({"error": "artist_a and artist_b required"}), 400
        # Get connections for both artists and find overlap
        conns_a = _lore_engine.get_artist_connections(artist_a)
        conns_b = _lore_engine.get_artist_connections(artist_b)
        result = {"artist_a": {"name": artist_a, "connections": conns_a}, "artist_b": {"name": artist_b, "connections": conns_b}}
        return jsonify({"result": _json_safe(result)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — DNA (sound fingerprinting)
# ---------------------------------------------------------------------------

@bp.route("/api/dna/trace", methods=["POST"])
def api_dna_trace():
    """Trace the sonic DNA of a track or artist."""
    if _dna_engine is None:
        return jsonify({"error": "DNA engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        track_id = data.get("track_id")
        artist = data.get("artist", "")
        if not track_id and not artist:
            return jsonify({"error": "track_id or artist required"}), 400
        if track_id:
            result = _dna_engine.trace_samples(track_id)
        else:
            result = []  # DNA trace requires a track_id
        return jsonify({"result": _json_safe(result)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/dna/pivot", methods=["POST"])
def api_dna_pivot():
    """Find pivot tracks that bridge two sonic spaces."""
    if _dna_engine is None:
        return jsonify({"error": "DNA engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        from_id = data.get("from_id", "")
        to_id = data.get("to_id", "")
        if not from_id or not to_id:
            return jsonify({"error": "from_id and to_id required"}), 400
        n = sanitize_integer(data.get("n", 5), default=5, min_val=1, max_val=20)
        result_from = _dna_engine.pivot_to_original(from_id)
        result_to = _dna_engine.pivot_to_original(to_id)
        result = {"from": _json_safe(result_from), "to": _json_safe(result_to)}
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Hunter (acquisition intelligence)
# ---------------------------------------------------------------------------

@bp.route("/api/hunter/hunt", methods=["POST"])
def api_hunter_hunt():
    """Hunt for music matching a description."""
    if _hunter_engine is None:
        return jsonify({"error": "Hunter engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        query = data.get("query", "")
        if not query:
            return jsonify({"error": "query required"}), 400
        n = sanitize_integer(data.get("n", 20), default=20, min_val=1, max_val=100)
        result = _hunter_engine.hunt(query)
        return jsonify({"result": _json_safe(result)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/hunter/acquire", methods=["POST"])
def api_hunter_acquire():
    """Queue acquisition for hunter results."""
    if _hunter_engine is None:
        return jsonify({"error": "Hunter engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        tracks = data.get("tracks", [])
        if not tracks:
            return jsonify({"error": "tracks list required"}), 400
        # Queue tracks for acquisition via the standard queue
        from oracle.db.schema import get_connection as _get_conn
        conn = _get_conn(timeout=10.0)
        cursor = conn.cursor()
        queued = 0
        for t in tracks:
            artist = (t.get("artist") or "").strip()
            title = (t.get("title") or "").strip()
            if not artist or not title:
                continue
            cursor.execute(
                "INSERT OR IGNORE INTO acquisition_queue (artist, title, source, status) VALUES (?, ?, 'hunter', 'pending')",
                (artist, title),
            )
            queued += cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({"result": {"queued": queued, "total": len(tracks)}})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Architect (structural analysis)
# ---------------------------------------------------------------------------

@bp.route("/api/architect/analyze", methods=["POST"])
def api_architect_analyze():
    """Analyze collection gaps and make acquisition recommendations."""
    if _architect_engine is None:
        return jsonify({"error": "Architect engine unavailable"}), 503
    try:
        data = request.get_json() or {}
        focus = data.get("focus", "gaps")  # "gaps" | "depth" | "diversity"
        # Architect doesn't have a general analyze(), do a library gap analysis
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'active'")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM track_scores")
        scored = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embedded = cursor.fetchone()[0]
        conn.close()
        result = {"focus": focus, "total_tracks": total, "scored": scored, "embedded": embedded, "gaps": {"unscored": total - scored, "unembedded": total - embedded}}
        return jsonify({"result": _json_safe(result)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/structure/<path:track_id>", methods=["GET"])
def api_structure_track(track_id: str):
    """Return structural analysis of a single track (section, BPM, key, etc.)."""
    try:
        conn = get_connection(timeout=10.0)
        track = _load_track(conn, track_id)
        if track is None:
            conn.close()
            return jsonify({"error": "Track not found"}), 404

        if _architect_engine is not None:
            try:
                filepath = track[7] if len(track) > 7 else ""
                structure = _architect_engine.analyze_structure(track_id, str(filepath))
            except Exception:
                structure = {}
        else:
            structure = {}

        payload = _track_row_to_dict(track)
        payload["structure"] = structure
        conn.close()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
