"""Core blueprint — health, status, doctor, cache stats, root."""

from __future__ import annotations

import time
import traceback
from pathlib import Path

from flask import Blueprint, jsonify, request

from oracle.api import VERSION
from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection
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

        llm_status: dict = {}
        try:
            from oracle.llm import get_llm_status
            llm_status = get_llm_status()
        except Exception:
            llm_status = {"status": "unavailable"}

        return jsonify({
            "status": "ok",
            "version": VERSION,
            "database": db,
            "library": lib,
            "llm": llm_status,
            "features": _feature_flags(),
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
    """API root."""
    return jsonify({
        "service": "lyra-oracle",
        "status": "ok",
        "version": VERSION,
        "message": "UI removed; use API endpoints under /api/*",
    })
