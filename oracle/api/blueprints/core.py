"""Core blueprint — health, status, doctor, cache stats, root."""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

from oracle.api import VERSION
from oracle.config import LIBRARY_BASE
from oracle.data_root_migration import (
    build_data_root_report,
    get_defer_payload,
    migrate_legacy_data,
)
from oracle.db.schema import get_connection, get_write_mode
from oracle.provider_health import get_all_health as _get_provider_health
from oracle.validation import sanitize_integer, validate_boolean

bp = Blueprint("core", __name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db_health() -> dict:
    try:
        conn = get_connection(timeout=5.0)
        cursor = conn.cursor()
        track_count = cursor.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        vibe_count = cursor.execute("SELECT COUNT(*) FROM vibe_profiles").fetchone()[0]
        conn.close()
        return {
            "ok": True,
            "track_count": int(track_count or 0),
            "vibe_count": int(vibe_count or 0),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _library_health() -> dict:
    try:
        base = Path(LIBRARY_BASE)
        return {"ok": base.exists(), "path": str(base), "exists": base.exists()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _feature_flags() -> dict:
    def _available(module: str, attr: str) -> bool:
        try:
            import importlib
            mod = importlib.import_module(module)
            return getattr(mod, attr, None) is not None
        except Exception:
            return False

    return {
        "agent": _available("oracle.agent", "agent"),
        "radio": _available("oracle.radio", "radio"),
        "dna": _available("oracle.dna", "dna"),
        "lore": _available("oracle.lore", "lore"),
        "architect": _available("oracle.architect", "architect"),
        "pipeline": _available("oracle.pipeline", "get_pipeline"),
        "auth_required": bool(__import__("os").getenv("LYRA_API_TOKEN", "").strip()),
    }


def _auth_config() -> dict:
    token = os.getenv("LYRA_API_TOKEN", "").strip()
    return {"enabled": bool(token)}


def _cors_config() -> dict:
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,null",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins or origins == ["*"]:
        origins = ["*"]
    return {"allowed_origins": origins}


def _acquisition_bootstrap_status() -> dict:
    """Return startup tier availability snapshot (non-blocking, no Docker boot)."""
    try:
        from oracle.acquirers.bootstrap_status import get_snapshot

        return get_snapshot()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "degraded",
            "docker_required": False,
            "error": str(exc),
            "tiers": {},
            "available_tiers": 0,
            "total_tiers": 0,
        }


def _runtime_services_status() -> dict:
    """Return runtime packaging/service policy for the active architecture."""
    try:
        from oracle.runtime_services import get_packaging_summary, get_runtime_service_manifest

        return {
            "manifest": get_runtime_service_manifest(),
            "packaging": get_packaging_summary(),
            "core_requires_docker": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "manifest": {},
            "packaging": {},
            "core_requires_docker": False,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/health", methods=["GET"])
def health():
    """Bare health check (no auth required)."""
    return jsonify({"status": "ok"})


@bp.route("/api/health", methods=["GET"])
def api_health():
    """Detailed health check."""
    try:
        db = _db_health()
        lib = _library_health()
        feature_flags = _feature_flags()
        auth = _auth_config()
        cors = _cors_config()

        llm_status: dict = {}
        try:
            from oracle.llm import get_llm_status
            llm_status = get_llm_status()
        except Exception:
            llm_status = {"status": "unavailable"}

        ok = bool(db.get("ok")) and bool(lib.get("ok"))
        timestamp = int(time.time())

        return jsonify({
            "status": "ok",
            "ok": ok,
            "service": "lyra-oracle",
            "version": VERSION,
            "timestamp": timestamp,
            "profile": os.getenv("LYRA_PROFILE", "default").strip() or "default",
            "write_mode": get_write_mode(),
            # Canonical keys used by current desktop schemas.
            "db": db,
            "database": db,
            "library": lib,
            "feature_flags": feature_flags,
            "acquisition": _acquisition_bootstrap_status(),
            "runtime_services": _runtime_services_status(),
            "data_root": build_data_root_report(),
            "llm": llm_status,
            "recommendation_providers": _get_provider_health(),
            "auth": auth,
            "cors": cors,
            # Backward compatibility for existing consumers/tests.
            "features": feature_flags,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/doctor", methods=["GET"])
def api_doctor():
    """Run system diagnostics."""
    try:
        from oracle.doctor import run_doctor
        report = run_doctor()
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/status", methods=["GET"])
def api_status():
    """Concise system status snapshot."""
    try:
        db = _db_health()
        lib = _library_health()

        llm_info: dict = {}
        try:
            from oracle.llm import get_llm_status
            llm_info = get_llm_status()
        except Exception:
            llm_info = {"status": "unavailable"}

        return jsonify({
            "status": "ok",
            "version": VERSION,
            "database": db,
            "library": lib,
            "acquisition": _acquisition_bootstrap_status(),
            "runtime_services": _runtime_services_status(),
            "data_root": build_data_root_report(),
            "llm": llm_info,
            "recommendation_providers": _get_provider_health(),
            "features": _feature_flags(),
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/runtime/services", methods=["GET"])
def api_runtime_services():
    """Return runtime-service packaging policy and active architecture manifest."""
    try:
        return jsonify(_runtime_services_status())
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/runtime/data-root", methods=["GET"])
def api_runtime_data_root():
    """Return the active data-root contract state and migration guidance."""
    try:
        return jsonify(build_data_root_report())
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/runtime/data-root/migrate", methods=["POST"])
def api_runtime_data_root_migrate():
    """Copy detected legacy runtime data into the active data root."""
    try:
        body = request.get_json(silent=True) or {}
        valid, error, overwrite = validate_boolean(body.get("overwrite", False), "overwrite")
        if not valid:
            return jsonify({"error": error}), 400
        return jsonify(migrate_legacy_data(overwrite=bool(overwrite)))
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/runtime/data-root/defer", methods=["POST"])
def api_runtime_data_root_defer():
    """Return the explicit temporary legacy-override instructions."""
    try:
        payload = get_defer_payload()
        payload["data_root"] = build_data_root_report()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/cache/stats", methods=["GET"])
def api_cache_stats():
    """Report provider-cache coverage and freshness from enrich_cache."""
    try:
        stale_seconds = sanitize_integer(
            request.args.get("stale_seconds", 1209600),
            default=1209600, min_val=60, max_val=31536000,
        )
        provider = (request.args.get("provider") or "").strip()
        now = time.time()

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where = ""
        params: list = []
        if provider:
            where = "WHERE provider = ?"
            params.append(provider)

        cursor.execute(
            f"""
            SELECT provider,
                   COUNT(*) AS total,
                   SUM(CASE WHEN fetched_at IS NULL THEN 1 ELSE 0 END) AS missing_ts,
                   MIN(fetched_at) AS min_fetched_at,
                   MAX(fetched_at) AS max_fetched_at
            FROM enrich_cache
            {where}
            GROUP BY provider
            ORDER BY total DESC
            """,
            params,
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            p, total, missing_ts, min_ts, max_ts = row
            stale_count = 0
            if stale_seconds > 0:
                cursor.execute(
                    "SELECT COUNT(*) FROM enrich_cache WHERE provider = ? AND fetched_at IS NOT NULL AND fetched_at < ?",
                    (p, now - stale_seconds),
                )
                stale_count = int(cursor.fetchone()[0] or 0)
            results.append({
                "provider": p,
                "total": int(total or 0),
                "missing_timestamp": int(missing_ts or 0),
                "stale": stale_count,
                "min_fetched_at": min_ts,
                "max_fetched_at": max_ts,
            })

        conn.close()
        return jsonify({
            "providers": results,
            "count": len(results),
            "stale_seconds": stale_seconds,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/stats/revelations", methods=["GET"])
def api_stats_revelations():
    """Return the north-star metric: tracks that were recommended then replayed within N days.

    A revelation is a track that:
    - Received a positive recommendation feedback (queue / accept / replay)
    - Was subsequently played in playback_history within ``window_days`` days

    Query params:
    - window_days (int, default 7): replay window after recommendation
    - limit (int, default 50): max tracks to return in the detail list
    """
    try:
        window_days = sanitize_integer(
            request.args.get("window_days", 7),
            default=7, min_val=1, max_val=90,
        )
        limit = sanitize_integer(
            request.args.get("limit", 50),
            default=50, min_val=1, max_val=500,
        )
        window_seconds = window_days * 24 * 3600

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()

        # Summary: distinct revelations in the last 7 days and 30 days
        cursor.execute(
            """
            SELECT COUNT(DISTINCT rf.track_id)
            FROM recommendation_feedback rf
            JOIN playback_history pb ON pb.track_id = rf.track_id
            WHERE rf.feedback_type IN ('queue', 'accept', 'replay')
              AND pb.ts BETWEEN rf.created_at AND (rf.created_at + ?)
              AND rf.created_at >= (strftime('%s', 'now') - ?)
            """,
            (window_seconds, window_seconds),
        )
        count_this_window = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(DISTINCT rf.track_id)
            FROM recommendation_feedback rf
            JOIN playback_history pb ON pb.track_id = rf.track_id
            WHERE rf.feedback_type IN ('queue', 'accept', 'replay')
              AND pb.ts BETWEEN rf.created_at AND (rf.created_at + ?)
            """,
            (window_seconds,),
        )
        count_all_time = int(cursor.fetchone()[0] or 0)

        # Detail: most recent revelations
        cursor.execute(
            """
            SELECT
                rf.track_id,
                rf.artist,
                rf.title,
                rf.feedback_type,
                rf.created_at AS recommended_at,
                MIN(pb.ts) AS first_replayed_at,
                COUNT(pb.id) AS replay_count
            FROM recommendation_feedback rf
            JOIN playback_history pb ON pb.track_id = rf.track_id
            WHERE rf.feedback_type IN ('queue', 'accept', 'replay')
              AND pb.ts BETWEEN rf.created_at AND (rf.created_at + ?)
            GROUP BY rf.track_id, rf.artist, rf.title, rf.feedback_type, rf.created_at
            ORDER BY rf.created_at DESC
            LIMIT ?
            """,
            (window_seconds, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        revelations = [
            {
                "track_id": row[0],
                "artist": row[1],
                "title": row[2],
                "feedback_type": row[3],
                "recommended_at": row[4],
                "first_replayed_at": row[5],
                "replay_count": int(row[6] or 0),
            }
            for row in rows
        ]

        return jsonify({
            "window_days": window_days,
            "count_this_window": count_this_window,
            "count_all_time": count_all_time,
            "revelations": revelations,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/")
def index():
    """Serve the built React UI if it exists, otherwise return API info."""
    import os
    from pathlib import Path as _Path
    dist_index = _Path(__file__).resolve().parents[3] / "desktop" / "renderer-app" / "dist" / "index.html"
    if dist_index.exists():
        from flask import send_from_directory as _sfd
        return _sfd(str(dist_index.parent), "index.html")
    return jsonify({
        "service": "lyra-oracle",
        "status": "ok",
        "version": VERSION,
        "hint": "Build the UI: cd desktop/renderer-app && npm install && npm run build",
        "player_test": "/player",
    })


@bp.route("/player")
def player_test():
    """Minimal in-browser audio player — picks a random track from the library."""
    try:
        conn = get_connection(timeout=5.0)
        c = conn.cursor()
        c.execute(
            "SELECT track_id, artist, title, album FROM tracks WHERE status='active' ORDER BY RANDOM() LIMIT 20"
        )
        rows = c.fetchall()
        conn.close()
    except Exception:
        rows = []

    track_options = ""
    for tid, artist, title, album in rows:
        label = f"{artist or '?'} — {title or '?'}"
        if album:
            label += f" [{album}]"
        track_options += f'<option value="{tid}">{label}</option>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Lyra Oracle — Player Test</title>
<style>
  body {{ background:#111; color:#eee; font-family:system-ui,sans-serif; max-width:600px; margin:40px auto; padding:16px; }}
  h1 {{ color:#a78bfa; }}
  select,audio {{ width:100%; margin:8px 0; }}
  audio {{ background:#222; border-radius:8px; }}
  .meta {{ color:#888; font-size:.85rem; margin:4px 0; }}
  a {{ color:#a78bfa; }}
</style>
</head>
<body>
<h1>Lyra Oracle — Audio Test</h1>
<p class="meta">FLAC → frag-mp4/AAC (256k) · on-the-fly ffmpeg transcode · <a href="/api/health">API health</a></p>
<select id="sel" onchange="play()">
  <option value="">— Pick a track —</option>
  {track_options}
</select>
<audio id="player" controls preload="none">Your browser does not support audio.</audio>
<p id="info" class="meta"></p>
<script>
function play() {{
  var sel = document.getElementById('sel');
  var tid = sel.value;
  if (!tid) return;
  var url = '/api/stream/' + tid;
  var p = document.getElementById('player');
  p.src = url;
  p.load();
  p.play().catch(function(e){{ document.getElementById('info').textContent = 'Autoplay blocked — press ▶'; }});
  document.getElementById('info').textContent = 'Streaming: /api/stream/' + tid;
}}
</script>
</body>
</html>"""
    from flask import make_response
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html"
    return resp


@bp.route("/<path:path>")
def react_static(path: str):
    """Serve React build static assets and handle SPA client-side routes."""
    from pathlib import Path as _Path
    from flask import send_from_directory as _sfd
    dist_dir = _Path(__file__).resolve().parents[3] / "desktop" / "renderer-app" / "dist"
    if not dist_dir.exists():
        return jsonify({"error": "UI not built"}), 404
    # Serve the exact file if it exists (JS, CSS, images, fonts, etc.)
    candidate = dist_dir / path
    if candidate.exists() and candidate.is_file():
        return _sfd(str(dist_dir), path)
    # SPA fallback: re-serve index.html for all client-side routes
    return _sfd(str(dist_dir), "index.html")
