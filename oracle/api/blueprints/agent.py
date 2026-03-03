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
