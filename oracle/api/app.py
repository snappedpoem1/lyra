"""Flask application factory and CLI entry-point for the Lyra Oracle API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import time

from dotenv import load_dotenv
from flask import Flask

from oracle.db.schema import get_write_mode

VERSION = "1.0.0"
logger = logging.getLogger(__name__)


def _should_prewarm_clap() -> bool:
    return os.getenv("LYRA_CLAP_PREWARM", "0").strip().lower() in {"1", "true", "yes", "on"}


def _run_clap_prewarm() -> None:
    t0 = time.perf_counter()
    try:
        from oracle.search import _get_clap_embedder
        from oracle.scorer import _anchor_embeddings, _get_embedder

        # Warm both query-time and scoring-time CLAP paths.
        _get_clap_embedder()
        _get_embedder()
        _anchor_embeddings()
        logger.info("[warmup] CLAP prewarm complete in %.2fs", time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[warmup] CLAP prewarm failed: %s", exc)


def _maybe_start_clap_prewarm() -> None:
    if not _should_prewarm_clap():
        return
    mode = os.getenv("LYRA_CLAP_PREWARM_MODE", "background").strip().lower()
    if mode in {"sync", "blocking"}:
        _run_clap_prewarm()
        return
    thread = threading.Thread(target=_run_clap_prewarm, name="clap-prewarm", daemon=True)
    thread.start()


def create_app() -> Flask:
    """Create, configure, and return the Flask application."""
    load_dotenv(override=False)

    # Point HuggingFace cache at the project-local directory so models are
    # never downloaded to a user home directory on a shared machine.
    project_root = Path(__file__).resolve().parent.parent.parent
    hf_home = str(project_root / "hf_cache")
    os.environ.setdefault("HF_HOME", hf_home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

    app = Flask(__name__)

    from oracle.api.cors import init_cors
    from oracle.api.auth import init_auth
    from oracle.api.registry import register_blueprints
    from oracle.api.scheduler import init_scheduler

    init_cors(app)
    init_auth(app)
    register_blueprints(app)
    init_scheduler(app)
    try:
        # Bootstrap acquisition tier visibility without starting Docker/services.
        from oracle.acquirers.bootstrap_status import start_background_refresh

        start_background_refresh()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[acquisition-bootstrap] startup refresh failed: %s", exc)
    _maybe_start_clap_prewarm()

    return app


def main() -> None:
    """Bootstrap runtime services, print startup header, start Flask dev server."""
    if os.getenv("LYRA_BOOTSTRAP", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            from oracle.bootstrap import bootstrap_runtime

            result = bootstrap_runtime(timeout_seconds=int(os.getenv("LYRA_BOOTSTRAP_TIMEOUT", "40")))
            external_services = result.get("external_services", {})
            llm = result.get("llm", {})
            logger.info(
                "[bootstrap] legacy external services: %s",
                "ready" if external_services.get("ready") else "not ready",
            )
            if external_services.get("error"):
                logger.warning("[bootstrap] legacy external detail: %s", external_services.get("error"))
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
    print("\nStarting server at http://localhost:5000")
    print("=" * 60 + "\n")

    app = create_app()

    debug_value = (os.getenv("LYRA_DEBUG", "") or os.getenv("FLASK_DEBUG", "")).strip().lower()
    app.run(host="0.0.0.0", port=5000, debug=debug_value in {"1", "true", "yes"})
