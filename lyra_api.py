"""Lyra Oracle Flask API server."""

from __future__ import annotations

from pathlib import Path
import logging
import os
import subprocess
import sys
import time
from typing import Dict, List
import json
import traceback
import sqlite3

from dotenv import load_dotenv
from oracle.config import (
    LOG_ROOT,
    MODEL_CACHE_HUB_ROOT,
    MODEL_CACHE_ROOT,
    PROJECT_ROOT,
    ensure_generated_dirs,
    log_legacy_data_warning,
)


def _configure_runtime_logging() -> None:
    """Configure a file logger for frozen/runtime builds."""
    log_path_raw = os.getenv("LYRA_BACKEND_LOG_PATH", "").strip()
    if not getattr(sys, "frozen", False) and not log_path_raw:
        return

    if log_path_raw:
        log_path = Path(log_path_raw)
    else:
        log_path = LOG_ROOT / "packaged-backend.log"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )

_configure_runtime_logging()
logger = logging.getLogger(__name__)


def _running_as_script() -> bool:
    if getattr(sys, "frozen", False):
        return False
    try:
        return Path(sys.argv[0]).resolve() == Path(__file__).resolve()
    except Exception:
        return False


def _maybe_reexec_in_project_venv() -> None:
    if not _running_as_script():
        return
    if os.getenv("LYRA_SKIP_VENV_REEXEC", "").strip().lower() in {"1", "true", "yes"}:
        return
    if os.getenv("LYRA_VENV_REEXEC", "").strip() == "1":
        return

    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    venv_python = next((candidate for candidate in candidates if candidate.exists()), None)
    if not venv_python:
        return

    try:
        current_python = Path(sys.executable).resolve()
    except Exception:
        current_python = Path(sys.executable)

    try:
        if current_python.samefile(venv_python):
            return
    except Exception:
        if str(current_python).lower() == str(venv_python).lower():
            return

    env = os.environ.copy()
    env["LYRA_VENV_REEXEC"] = "1"
    print(f"[runtime] switching to project virtualenv: {venv_python}", flush=True)
    completed = subprocess.run(
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        env=env,
        cwd=str(PROJECT_ROOT),
    )
    raise SystemExit(completed.returncode)


_maybe_reexec_in_project_venv()
load_dotenv(override=False)
ensure_generated_dirs()
hf_home = str(MODEL_CACHE_ROOT)
os.environ.setdefault("HF_HOME", hf_home)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(MODEL_CACHE_HUB_ROOT))
log_legacy_data_warning()

# ---------------------------------------------------------------------------
# Everything below this line runs inside the project virtualenv.
# The full API is implemented in oracle/api/ using Flask Blueprints.
# ---------------------------------------------------------------------------

from oracle.api import create_app, main  # noqa: E402

# Background workers (APScheduler) are started inside create_app() via init_scheduler().
logger.info("[lyra_api] project_root=%s frozen=%s", PROJECT_ROOT, getattr(sys, "frozen", False))
app = create_app()
logger.info("[lyra_api] routes=%s", app.url_map)

if __name__ == "__main__":
    main()
