"""Core blueprint — health, status, doctor, cache stats, root."""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

from oracle.api import VERSION
from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection, get_write_mode
from oracle.validation import sanitize_integer

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
            "llm": llm_status,
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
            "llm": llm_info,
            "features": _feature_flags(),
        })
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
