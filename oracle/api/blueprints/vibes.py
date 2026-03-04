"""Vibes / playlists / curation blueprint."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

from oracle.api.helpers import (
    _fallback_vibe_narrative,
    _load_vibe_detail,
    _playlist_run_to_dict,
)
from oracle.db.schema import get_connection
from oracle.validation import (
    sanitize_integer,
    validate_boolean,
    validate_name,
    validate_vibe_materialize_request,
    validate_vibe_save_request,
)

bp = Blueprint("vibes", __name__)

try:
    from oracle.llm import LLMClient
except Exception:
    LLMClient = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# LLM vibe helper
# ---------------------------------------------------------------------------

def _generate_vibe_from_prompt(prompt: str, n: int) -> dict:
    """Generate vibe metadata and CLAP query from a natural-language prompt."""
    prompt = prompt.strip()
    fallback_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
    fallback_name = fallback_name[:80]
    fallback = {
        "name": fallback_name,
        "query": prompt,
        "n": n,
        "narrative": "",
        "used_llm": False,
        "llm": {"status": "unavailable"},
    }
    if not LLMClient:
        return fallback
    try:
        client = LLMClient.from_env()
        status = client.check_available()
        llm_payload = status.as_dict()
        llm_payload["status"] = "ok" if status.ok else "unavailable"
        fallback["llm"] = llm_payload
        if not status.ok:
            return fallback

        result = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.35,
            max_tokens=220,
            json_schema={
                "name": "vibe_generation",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "query": {"type": "string"},
                        "n": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "narrative": {"type": "string"},
                    },
                    "required": ["name", "query", "n", "narrative"],
                    "additionalProperties": False,
                },
            },
            system=(
                "You build music vibe presets. Return a concise vibe name and a CLAP-friendly query "
                "that captures sound and mood (tempo, texture, instrumentation, energy)."
            ),
        )
        if not result.get("ok") or "data" not in result:
            return fallback

        payload = result["data"]
        name = (payload.get("name") or fallback_name).strip()[:80]
        query = (payload.get("query") or prompt).strip() or prompt
        count = sanitize_integer(payload.get("n", n), default=n, min_val=1, max_val=1000)
        narrative = (payload.get("narrative") or "").strip()
        return {
            "name": name,
            "query": query,
            "n": count,
            "narrative": narrative,
            "used_llm": True,
            "llm": llm_payload,
        }
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Routes — vibes
# ---------------------------------------------------------------------------

@bp.route("/api/vibes", methods=["GET"])
def api_vibes_list():
    """List all saved vibes."""
    try:
        from oracle.vibes import list_vibes
        vibes = list_vibes()
        return jsonify({"vibes": vibes, "count": len(vibes)})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/playlists/<playlist_id>", methods=["GET"])
def api_playlist_detail(playlist_id: str):
    """Return canonical playlist/listening-thread detail."""
    try:
        detail = _load_vibe_detail(playlist_id)
        if not detail:
            return jsonify({"error": "Playlist not found"}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/playlists/<int:run_id>/explain", methods=["GET"])
def api_playlist_explain(run_id: int):
    """Structured reasons for every track in a playlist run (F-007)."""
    try:
        from oracle.explain import ReasonBuilder
        rb = ReasonBuilder()
        result = rb.explain_run(run_id)
        if result["track_count"] == 0:
            return jsonify({"error": f"No tracks found for run_id {run_id}"}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/vibes/save", methods=["POST"])
def api_vibes_save():
    """Create a new named vibe from a query."""
    try:
        from oracle.vibes import save_vibe
        data = request.get_json() or {}
        valid, error, sanitized = validate_vibe_save_request(data)
        if not valid:
            return jsonify({"error": error}), 400
        result = save_vibe(sanitized["name"], sanitized["query"], n=sanitized["n"])
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/generate", methods=["POST"])
def api_vibes_generate():
    """Generate vibe query/name from natural-language prompt, optionally save."""
    try:
        from oracle.vibes import generate_vibe
        data = request.get_json() or {}
        prompt = (data.get("prompt") or data.get("query") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        n = sanitize_integer(data.get("n", 200), default=200, min_val=1, max_val=1000)
        valid, error, save_generated = validate_boolean(data.get("save", False), "save")
        if not valid:
            return jsonify({"error": error}), 400

        # Optional arc template for emotional journey sequencing
        arc = (data.get("arc") or "").strip() or None

        generated = _generate_vibe_from_prompt(prompt, n)
        candidate_name = generated.get("name", "").strip() or "Generated Vibe"
        if save_generated:
            valid_name, _ = validate_name(candidate_name, "Vibe name")
            if not valid_name:
                candidate_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
                candidate_name = candidate_name.replace("/", " ").replace("\\", " ").replace(":", " ")
                candidate_name = candidate_name[:80]

        run = generate_vibe(
            generated["query"],
            n=generated["n"],
            vibe_name=candidate_name if save_generated else None,
            arc=arc,
        )
        return jsonify({
            "meta": {
                "prompt": prompt,
                "generated": generated,
                "save_requested": save_generated,
                "vibe_name": candidate_name if save_generated else None,
            },
            "run": _playlist_run_to_dict(run),
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/create", methods=["POST"])
def api_vibes_create():
    """One-shot vibe creation with optional build and materialize."""
    try:
        from oracle.vibes import save_vibe, build_vibe, materialize_vibe
        data = request.get_json() or {}
        prompt = (data.get("prompt") or data.get("query") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        provided_name = (data.get("name") or "").strip()
        n = sanitize_integer(data.get("n", 200), default=200, min_val=1, max_val=1000)

        valid, error, do_build = validate_boolean(data.get("build", False), "build")
        if not valid:
            return jsonify({"error": error}), 400
        valid, error, do_materialize = validate_boolean(data.get("materialize", False), "materialize")
        if not valid:
            return jsonify({"error": error}), 400

        mode = (data.get("mode") or "hardlink").strip().lower()
        if mode not in ("hardlink", "symlink", "shortcut"):
            return jsonify({"error": "Invalid mode. Must be one of: hardlink, symlink, shortcut"}), 400

        generated = _generate_vibe_from_prompt(prompt, n)
        vibe_name = provided_name or (generated.get("name") or "").strip() or "Generated Vibe"
        valid_name, _ = validate_name(vibe_name, "Vibe name")
        if not valid_name:
            vibe_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
            vibe_name = vibe_name.replace("/", " ").replace("\\", " ").replace(":", " ")[:80]

        save_result = save_vibe(vibe_name, generated["query"], n=generated["n"])
        if "error" in save_result:
            return jsonify({"prompt": prompt, "generated": generated, "save": save_result}), 400

        response: dict = {"prompt": prompt, "name": vibe_name, "generated": generated, "save": save_result}

        if do_build:
            build_result = build_vibe(vibe_name)
            response["build"] = build_result
            if "error" in build_result:
                return jsonify(response), 400

        if do_materialize:
            materialize_result = materialize_vibe(vibe_name, mode=mode)
            response["materialize"] = materialize_result
            if "error" in materialize_result:
                return jsonify(response), 400

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/narrate", methods=["POST"])
def api_vibes_narrate():
    """Generate an LLM narrative for a vibe's current ordered tracks."""
    try:
        if not LLMClient:
            return jsonify({"error": "LLM client unavailable"}), 503

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400

        arc_type = (data.get("arc_type") or "journey").strip() or "journey"
        limit = sanitize_integer(data.get("limit", 20), default=20, min_val=1, max_val=50)

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.artist, t.title
            FROM vibe_tracks vt
            JOIN tracks t ON vt.track_id = t.track_id
            WHERE vt.vibe_name = ?
            ORDER BY vt.position
            LIMIT ?
            """,
            (name, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return jsonify({"error": f'No tracks found for vibe "{name}"'}), 404

        tracks = [{"artist": r[0] or "", "title": r[1] or ""} for r in rows]
        client = LLMClient.from_env()
        llm_status = client.check_available()
        llm_payload = llm_status.as_dict()
        llm_payload["status"] = "ok" if llm_status.ok else "unavailable"
        if not llm_status.ok:
            return jsonify({
                "name": name, "arc_type": arc_type, "track_count": len(tracks),
                "narrative": _fallback_vibe_narrative(tracks, arc_type),
                "llm": llm_payload, "fallback": True,
            })

        narrative = client.narrate_playlist(tracks, arc_type=arc_type)
        return jsonify({
            "name": name, "arc_type": arc_type, "track_count": len(tracks),
            "narrative": narrative, "llm": llm_payload,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/build", methods=["POST"])
def api_vibes_build():
    """Build the M3U8 playlist for a vibe."""
    try:
        from oracle.vibes import build_vibe
        data = request.get_json() or {}
        name = data.get("name", "")
        if not name:
            return jsonify({"error": "Name is required"}), 400
        result = build_vibe(name)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/materialize", methods=["POST"])
def api_vibes_materialize():
    """Materialize a vibe as a folder of hardlinks/symlinks."""
    try:
        from oracle.vibes import materialize_vibe
        data = request.get_json() or {}
        valid, error, sanitized = validate_vibe_materialize_request(data)
        if not valid:
            return jsonify({"error": error}), 400
        result = materialize_vibe(sanitized["name"], mode=sanitized["mode"])
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/refresh", methods=["POST"])
def api_vibes_refresh():
    """Refresh one or all vibes."""
    try:
        from oracle.vibes import refresh_vibes
        data = request.get_json() or {}
        result = refresh_vibes(data.get("name"))
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/vibes/delete", methods=["POST"])
def api_vibes_delete():
    """Delete a vibe."""
    try:
        from oracle.vibes import delete_vibe
        data = request.get_json() or {}
        name = data.get("name", "")
        delete_folder = data.get("delete_folder", False)
        if not name:
            return jsonify({"error": "Name is required"}), 400
        result = delete_vibe(name, delete_materialized=delete_folder)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — curation
# ---------------------------------------------------------------------------

@bp.route("/api/curate/classify", methods=["POST"])
def api_curate_classify():
    """Classify all tracks."""
    try:
        from oracle.classifier import classify_library
        data = request.get_json() or {}
        limit = sanitize_integer(data.get("limit", 0), default=0, min_val=0, max_val=500000)
        valid, error, use_llm = validate_boolean(data.get("use_llm", False), "use_llm")
        if not valid:
            return jsonify({"error": error}), 400
        results = classify_library(limit=limit, use_llm=use_llm)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/curate/plan", methods=["POST"])
def api_curate_plan():
    """Generate curation plan."""
    try:
        from oracle.curator import generate_plan
        data = request.get_json() or {}
        result = generate_plan(
            preset=data.get("preset", "artist_album"),
            classify_first=data.get("classify_first", False),
            limit=data.get("limit", 0),
            output_dir="Reports",
        )
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/curate/apply", methods=["POST"])
def api_curate_apply():
    """Apply a curation plan."""
    try:
        from oracle.curator import apply_plan
        data = request.get_json() or {}
        plan_path = data.get("plan_path", "")
        if not plan_path:
            return jsonify({"error": "Plan path is required"}), 400
        result = apply_plan(
            plan_path=plan_path,
            confidence_min=data.get("confidence_min", 0.5),
            dry_run=data.get("dry_run", True),
        )
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
