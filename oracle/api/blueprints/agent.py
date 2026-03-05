"""Agent (Lyra), journal, and undo blueprint."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

from oracle.validation import validate_boolean

bp = Blueprint("agent", __name__)

# ---------------------------------------------------------------------------
# Lazy engine imports
# ---------------------------------------------------------------------------

try:
    from oracle.agent import AgentEngine as _AgentEngine
    _agent_engine = _AgentEngine()
except Exception:
    _agent_engine = None

try:
    from oracle.safety import get_journal, undo_last
except Exception:
    get_journal = None  # type: ignore[assignment]
    undo_last = None    # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Routes — Agent
# ---------------------------------------------------------------------------

@bp.route("/api/agent/query", methods=["POST"])
def api_agent_query():
    """Query Lyra agent for orchestration."""
    if _agent_engine is None:
        return jsonify({"error": "Agent engine not available"}), 503
    try:
        data = request.get_json() or {}
        text = (data.get("text") or data.get("query") or "").strip()
        context = data.get("context") or {}
        valid, error, execute = validate_boolean(data.get("execute", False), "execute")
        if not valid:
            return jsonify({"error": error}), 400
        if not text:
            return jsonify({"error": "text is required"}), 400
        if execute:
            result = _agent_engine.query(text, context=context)
        else:
            result = _agent_engine.run_agent(text, context=context)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/agent/fact-drop", methods=["GET"])
def api_agent_fact_drop():
    """Get a fact-drop for a track."""
    if _agent_engine is None:
        return jsonify({"error": "Agent engine not available"}), 503
    try:
        track_id = (request.args.get("track_id") or "").strip()
        if not track_id:
            return jsonify({"error": "track_id is required"}), 400
        fact = _agent_engine.fact_drop(track_id)
        return jsonify({"track_id": track_id, "fact": fact})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/agent/suggest", methods=["GET"])
def api_agent_suggest():
    """Get proactive next-action suggestion from Lyra agent."""
    if _agent_engine is None:
        return jsonify({"error": "Agent engine not available"}), 503
    try:
        context: dict = {}
        track_id = (request.args.get("track_id") or "").strip()
        if track_id:
            context["current_track"] = track_id
        result = _agent_engine.suggest_next_action(context)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/agent/briefing", methods=["GET"])
def api_agent_briefing():
    """Daily Oracle briefing — new tracks, taste-aligned queue items, radio seed."""
    try:
        from oracle.db.schema import get_connection as _gc
        conn = _gc(timeout=10.0)
        cursor = conn.cursor()

        # New tracks added in last 24h
        cursor.execute(
            "SELECT COUNT(*) FROM tracks WHERE status='active' AND rowid > "
            "(SELECT COALESCE(MAX(rowid),0) FROM tracks WHERE status='active') - 200"
        )
        # simpler: tracks added in last 24h via timestamp if available, else just top-5 newest
        cursor.execute(
            "SELECT artist, title FROM tracks WHERE status='active' ORDER BY rowid DESC LIMIT 5"
        )
        newest = [{"artist": r[0], "title": r[1]} for r in cursor.fetchall()]

        # Taste profile snapshot
        cursor.execute("SELECT dimension, value, confidence FROM taste_profile ORDER BY confidence DESC")
        taste_rows = cursor.fetchall()
        taste = {r[0]: {"value": round(float(r[1]), 3), "confidence": round(float(r[2]), 3)} for r in taste_rows}

        # Top taste-aligned acquisition queue items
        cursor.execute(
            "SELECT artist, title, priority FROM acquisition_queue "
            "WHERE status='pending' ORDER BY priority DESC LIMIT 10"
        )
        queue_top = [{"artist": r[0], "title": r[1], "priority": round(float(r[2] or 5.0), 2)}
                     for r in cursor.fetchall()]

        # Playback stats
        cursor.execute("SELECT COUNT(*) FROM playback_history")
        playback_total = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM tracks WHERE status='active'")
        library_total = cursor.fetchone()[0] or 0

        conn.close()

        return jsonify({
            "newest_tracks": newest,
            "taste_snapshot": taste,
            "top_queue_items": queue_top,
            "playback_total": playback_total,
            "library_total": library_total,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/acquire/prioritize", methods=["POST"])
def api_acquire_prioritize():
    """Re-score acquisition queue by taste alignment."""
    try:
        data = request.get_json() or {}
        limit = int(data.get("limit", 0))
        from oracle.acquirers.taste_prioritizer import prioritize_queue
        stats = prioritize_queue(limit=limit)
        return jsonify({"ok": True, **stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — Journal / Undo
# ---------------------------------------------------------------------------

@bp.route("/api/journal", methods=["GET"])
def api_journal():
    """Get operation history from journal."""
    if get_journal is None:
        return jsonify({"error": "Safety module not available"}), 503
    try:
        n = int(request.args.get("n", 10))
        journal = get_journal()
        transactions = journal.read_last(n)
        return jsonify({"count": len(transactions), "transactions": [txn.to_dict() for txn in transactions]})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/undo", methods=["POST"])
def api_undo():
    """Undo last N file operations."""
    if undo_last is None:
        return jsonify({"error": "Safety module not available"}), 503
    try:
        data = request.get_json() or {}
        n = int(data.get("n", 1))
        undone = undo_last(n)
        return jsonify({
            "success": True,
            "undone_count": len(undone),
            "transactions": [txn.to_dict() for txn in undone],
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
