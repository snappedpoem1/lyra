"""Flask application factory and CLI entry-point for the Lyra Oracle API.

This module is the *spine*: it wires ribs together and nothing else.
Business logic lives in the rib modules and blueprints; this file should
rarely need to change.

Ribs:
  oracle.api.cors       — CORS initialisation
  oracle.api.auth       — bearer-token before_request middleware
  oracle.api.registry   — fault-tolerant blueprint registration
  oracle.api.scheduler  — embedded APScheduler (BackgroundScheduler)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from oracle.db.schema import get_write_mode

VERSION = "1.0.0"
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create, configure, and return the Flask application.

    Calls each rib's ``init_*`` / ``register_*`` function in order.
    Rib failures are handled within the ribs themselves — a broken rib
    degrades gracefully rather than crashing the factory.

    Returns:
        Configured :class:`flask.Flask` instance.
    """
    load_dotenv(override=False)

    # Point HuggingFace cache at the project-local directory so models are
    # never downloaded to a user home directory on a shared machine.
    project_root = Path(__file__).resolve().parent.parent.parent
    hf_home = str(project_root / "hf_cache")
    os.environ.setdefault("HF_HOME", hf_home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

    app = Flask(__name__)

    # ── Ribs ──────────────────────────────────────────────────────────────
    from oracle.api.cors import init_cors
    from oracle.api.auth import init_auth
    from oracle.api.registry import register_blueprints
    from oracle.api.scheduler import init_scheduler

    init_cors(app)
    init_auth(app)
    register_blueprints(app)
    init_scheduler(app)   # embedded BackgroundScheduler — no separate process needed

    return app


def main() -> None:
    """Bootstrap runtime services, print startup header, start Flask dev server."""
    if os.getenv("LYRA_BOOTSTRAP", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            from oracle.bootstrap import bootstrap_runtime
            result = bootstrap_runtime(
                timeout_seconds=int(os.getenv("LYRA_BOOTSTRAP_TIMEOUT", "40"))
            )
            docker = result.get("docker", {})
            llm = result.get("llm", {})
            logger.info("[bootstrap] docker: %s", "ready" if docker.get("ready") else "not ready")
            if docker.get("error"):
                logger.warning("[bootstrap] docker detail: %s", docker.get("error"))
            logger.info("[bootstrap] lm studio: %s", "ready" if llm.get("ready") else "not ready")
            if llm.get("error"):
                logger.warning("[bootstrap] lm detail: %s", llm.get("error"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[bootstrap] warning: %s", exc)

    print("\n" + "=" * 60)
    print("LYRA ORACLE API SERVER")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print(f"Write Mode: {get_write_mode()}")
    print(f"\nStarting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app = create_app()

    debug_value = (
        os.getenv("LYRA_DEBUG", "") or os.getenv("FLASK_DEBUG", "")
    ).strip().lower()
    app.run(host="0.0.0.0", port=5000, debug=debug_value in {"1", "true", "yes"})
