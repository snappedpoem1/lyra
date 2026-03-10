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
    from oracle.scout import ScoutEngine as _ScoutEngine
    _scout_engine = _ScoutEngine()
except Exception:
    _scout_engine = None

try:
    from oracle.lore import LoreEngine as _LoreEngine
    _lore_engine = _LoreEngine()
except Exception:
    _lore_engine = None

try:
    from oracle.dna import DNAEngine as _DNAEngine
    _dna_engine = _DNAEngine()
except Exception:
    _dna_engine = None

try:
    from oracle.hunter import HunterEngine as _HunterEngine
    _hunter_engine = _HunterEngine()
except Exception:
    _hunter_engine = None

try:
    from oracle.architect import ArchitectEngine as _ArchitectEngine
    _architect_engine = _ArchitectEngine()
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
        track_id = data.get("track_id", "")
        if not track_id:
            return jsonify({"error": "track_id required"}), 400
        n = sanitize_integer(data.get("n", 10), default=10, min_val=1, max_val=100)
        results = _scout_engine.cross_genre(track_id, n=n)
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
        result = _lore_engine.trace(artist, depth=depth)
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
        result = _lore_engine.connections(artist_a, artist_b)
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
        result = _dna_engine.trace(track_id=track_id, artist=artist)
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
        result = _dna_engine.pivot(from_id, to_id, n=n)
        return jsonify({"result": _json_safe(result)})
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
        result = _hunter_engine.hunt(query, n=n)
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
        result = _hunter_engine.queue_acquisition(tracks)
        return jsonify({"result": _json_safe(result)})
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
        result = _architect_engine.analyze(focus=focus)
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
                structure = _architect_engine.analyze_track(track_id)
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


# ---------------------------------------------------------------------------
# Routes — Duplicates
# ---------------------------------------------------------------------------

@bp.route("/api/duplicates/summary", methods=["GET"])
def api_duplicates_summary():
    """Return a summary count of duplicate groups detected by each strategy."""
    try:
        from oracle.duplicates import get_duplicate_summary
        threshold = float(request.args.get("threshold", 0.85))
        threshold = max(0.5, min(1.0, threshold))
        return jsonify(get_duplicate_summary(metadata_threshold=threshold))
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/duplicates", methods=["GET"])
def api_duplicates():
    """Return full duplicate groups from all three detection strategies.

    Query params:
    - strategy: ``exact`` | ``metadata`` | ``path`` | ``all`` (default ``all``)
    - threshold: float 0.5–1.0 for metadata strategy (default 0.85)
    """
    try:
        from oracle.duplicates import (
            find_exact_duplicates,
            find_metadata_duplicates,
            find_path_duplicates,
            find_all_duplicates,
        )
        strategy = (request.args.get("strategy") or "all").strip().lower()
        threshold = float(request.args.get("threshold", 0.85))
        threshold = max(0.5, min(1.0, threshold))

        if strategy == "exact":
            return jsonify({"exact": find_exact_duplicates()})
        if strategy == "metadata":
            return jsonify({"metadata": find_metadata_duplicates(threshold=threshold)})
        if strategy == "path":
            return jsonify({"path": find_path_duplicates()})
        return jsonify(find_all_duplicates(metadata_threshold=threshold))
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
