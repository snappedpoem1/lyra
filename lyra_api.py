"""Lyra Oracle Flask API server."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import time
from typing import Dict, List
import json
import traceback
import sqlite3

from dotenv import load_dotenv

def _resolve_project_root() -> Path:
    env_root = os.getenv("LYRA_PROJECT_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent


PROJECT_ROOT = _resolve_project_root()


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
hf_home = str(PROJECT_ROOT / "hf_cache")
os.environ.setdefault("HF_HOME", hf_home)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

# ---------------------------------------------------------------------------
# Everything below this line runs inside the project virtualenv.
# The full API is implemented in oracle/api/ using Flask Blueprints.
# ---------------------------------------------------------------------------

from oracle.api import create_app, main  # noqa: E402

# Background workers (APScheduler) are started inside create_app() via init_scheduler().
app = create_app()

if __name__ == "__main__":
    main()
