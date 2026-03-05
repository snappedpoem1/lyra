"""Oracle API package — Flask application factory.

Usage::

    # WSGI / gunicorn
    from oracle.api import create_app
    app = create_app()

    # Direct run
    from oracle.api import main
    main()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS

from oracle.db.schema import get_connection, get_write_mode

VERSION = "1.0.0"
logger = logging.getLogger(__name__)
_background_workers_started = False


def create_app() -> Flask:
    """Create and configure the Flask application."""
    load_dotenv(override=False)

    # Point HuggingFace cache at the project-local directory.
    project_root = Path(__file__).resolve().parent.parent.parent
    hf_home = str(project_root / "hf_cache")
    os.environ.setdefault("HF_HOME", hf_home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

    app = Flask(__name__)

    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,null",
        ).split(",")
        if origin.strip()
    ]
    CORS(app, resources={r"/api/*": {"origins": cors_origins or "*"}})

    api_token = os.getenv("LYRA_API_TOKEN", "").strip()

    @app.before_request
    def require_api_token() -> None:
        if not request.path.startswith("/api/"):
            return None
        if request.path == "/api/health":
            return None
        g.authenticated = not api_token
        if not api_token:
            return None
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header != f"Bearer {api_token}":
            return jsonify({"error": "Unauthorized", "status": 401}), 401
        g.authenticated = True
        return None

    # ── Register blueprints ────────────────────────────────────────────────
    from oracle.api.blueprints.core import bp as core_bp
    from oracle.api.blueprints.search import bp as search_bp
    from oracle.api.blueprints.library import bp as library_bp
    from oracle.api.blueprints.vibes import bp as vibes_bp
    from oracle.api.blueprints.acquire import bp as acquire_bp
    from oracle.api.blueprints.intelligence import bp as intelligence_bp
    from oracle.api.blueprints.radio import bp as radio_bp
    from oracle.api.blueprints.agent import bp as agent_bp
    from oracle.api.blueprints.pipeline import bp as pipeline_bp
    from oracle.api.blueprints.enrich import bp as enrich_bp
    from oracle.api.blueprints.discovery import bp as discovery_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(vibes_bp)
    app.register_blueprint(acquire_bp)
    app.register_blueprint(intelligence_bp)
    app.register_blueprint(radio_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(enrich_bp)
    app.register_blueprint(discovery_bp)

    return app


def ensure_runtime_background_workers() -> None:
    """No-op: recurring jobs are now owned by oracle/worker.py (APScheduler).

    Run the worker separately::

        python -m oracle.worker start
        oracle worker start

    Keeping this function present so existing call sites in main() don't break.
    """
    global _background_workers_started
    if _background_workers_started:
        return
    _background_workers_started = True
    logger.info(
        "[api] background jobs are handled by oracle.worker — "
        "start it with: python -m oracle.worker start"
    )


def main() -> None:
    """Bootstrap services, print header, start Flask development server."""
    if os.getenv("LYRA_BOOTSTRAP", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            from oracle.bootstrap import bootstrap_runtime
            result = bootstrap_runtime(
                timeout_seconds=int(os.getenv("LYRA_BOOTSTRAP_TIMEOUT", "40"))
            )
            docker = result.get("docker", {})
            llm = result.get("llm", {})
            print(f"[bootstrap] docker: {'ready' if docker.get('ready') else 'not ready'}")
            if docker.get("error"):
                print(f"[bootstrap] docker detail: {docker.get('error')}")
            print(f"[bootstrap] lm studio: {'ready' if llm.get('ready') else 'not ready'}")
            if llm.get("error"):
                print(f"[bootstrap] lm detail: {llm.get('error')}")
        except Exception as exc:
            print(f"[bootstrap] warning: {exc}")

    print("\n" + "=" * 60)
    print("LYRA ORACLE API SERVER")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print(f"Write Mode: {get_write_mode()}")
    print(f"\nStarting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app = create_app()
    ensure_runtime_background_workers()

    debug_value = (
        os.getenv("LYRA_DEBUG", "")
        or os.getenv("FLASK_DEBUG", "")
    ).strip().lower()
    app.run(host="0.0.0.0", port=5000, debug=debug_value in {"1", "true", "yes"})
