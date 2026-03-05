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
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS

from oracle.db.schema import get_connection, get_write_mode

VERSION = "1.0.0"
logger = logging.getLogger(__name__)
_background_workers_started = False
_playback_bridge = None


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


def _schedule_startup_jobs() -> None:
    """Kick off lightweight background jobs when the server boots.

    Checks for empty/sparse tables and fills them without blocking startup:
      - Taste profile: seed from library scores if no playback recorded yet
      - Artist graph: incremental build if connections table is empty
      - Biographer: enrich up to 50 new/stale artists if cache is empty
    """

    def _run() -> None:
        time.sleep(0.5)  # brief pause before startup jobs
        try:
            from oracle.db.schema import get_connection as _gc

            # 1. Taste seed
            _conn = _gc()
            _c = _conn.cursor()
            _c.execute("SELECT COUNT(*) FROM playback_history")
            playback_count = _c.fetchone()[0] or 0
            _c.execute("SELECT COUNT(*) FROM track_scores WHERE energy IS NOT NULL")
            scored_count = _c.fetchone()[0] or 0
            _c.execute("SELECT MAX(confidence) FROM taste_profile")
            max_conf = _c.fetchone()[0] or 0
            _conn.close()

            if scored_count > 0 and (playback_count == 0 or float(max_conf) < 0.5):
                try:
                    from oracle.taste import seed_taste_from_library
                    res = seed_taste_from_library()
                    print(f"[startup] Taste seeded from library: {len(res.get('seeded', []))} dimensions")
                except Exception as _e:
                    print(f"[startup] Taste seed error: {_e}")

            # 2. Artist graph (incremental)
            _conn2 = _gc()
            _c2 = _conn2.cursor()
            _c2.execute("SELECT COUNT(*) FROM connections")
            conn_count = _c2.fetchone()[0] or 0
            _conn2.close()

            if conn_count == 0:
                print("[startup] connections=0 — scheduling incremental graph build...")
                try:
                    from oracle.graph_builder import GraphBuilder
                    added = GraphBuilder().build_incremental()
                    print(f"[startup] Graph build complete: {added} edges added")
                except Exception as _e:
                    print(f"[startup] Graph build error: {_e}")

            # 3. Biographer (first 50 stale artists)
            _conn3 = _gc()
            _c3 = _conn3.cursor()
            _c3.execute("SELECT COUNT(*) FROM enrich_cache WHERE provider='biographer'")
            bio_count = _c3.fetchone()[0] or 0
            _conn3.close()

            if bio_count < 10:
                print(f"[startup] biographer_cache={bio_count} — enriching first 50 artists...")
                try:
                    from oracle.enrichers.biographer import Biographer
                    stats = Biographer().enrich_stale_artists(limit=50)
                    print(f"[startup] Biographer: {stats['processed']} enriched, {stats['failed']} failed")
                except Exception as _e:
                    print(f"[startup] Biographer error: {_e}")

        except Exception as _outer:
            print(f"[startup] auto-init error: {_outer}")

    threading.Thread(target=_run, name="lyra-startup-init", daemon=True).start()


def _schedule_playback_listener() -> None:
    """Start the BeefWeb playback bridge in the background when reachable."""

    def _run() -> None:
        global _playback_bridge

        if os.getenv("LYRA_AUTOSTART_PLAYBACK", "1").strip().lower() in {"0", "false", "no"}:
            print("[startup] playback listener autostart disabled")
            return

        time.sleep(2)
        try:
            from oracle.integrations.beefweb_bridge import BeefWebBridge

            host = os.getenv("BEEFWEB_HOST", "localhost")
            port = int(os.getenv("BEEFWEB_PORT", "8880"))
            bridge = BeefWebBridge(host=host, port=port)
            if not bridge.check_connection():
                print(f"[startup] BeefWeb not reachable at {host}:{port} - playback listener not started")
                return
            bridge.start_background()
            _playback_bridge = bridge
            print(f"[startup] PlayFaux bridge active via BeefWeb at {host}:{port}")
        except Exception as exc:
            print(f"[startup] playback listener error: {exc}")

    threading.Thread(target=_run, name="lyra-playback-listener", daemon=True).start()


def ensure_runtime_background_workers() -> None:
    """Start one-time background workers for the current process."""
    global _background_workers_started
    if _background_workers_started:
        return
    _background_workers_started = True
    _schedule_startup_jobs()
    _schedule_playback_listener()


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
