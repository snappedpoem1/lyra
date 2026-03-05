"""System diagnostics for Lyra Oracle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import List

from dotenv import load_dotenv
from oracle.llm_config import diagnose_llm_config, load_llm_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "lyra_registry.db"
CHROMA_PATH = PROJECT_ROOT / "chroma_storage"

REQUIRED_ENV_KEYS = [
    "MB_APP_NAME",
    "MB_APP_VERSION",
    "MB_CONTACT",
]


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARNING | FAIL
    details: str


# ---------------------------------------------------------------------------
# Infrastructure checks
# ---------------------------------------------------------------------------

def _check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    if major != 3 or minor < 12:
        return CheckResult("Python", "WARNING", f"Python {major}.{minor} â€” 3.12+ recommended")
    return CheckResult("Python", "PASS", f"Python {major}.{minor}")


def _check_tool(name: str, command: str, install_hint: str) -> CheckResult:
    found = shutil.which(command)
    if not found:
        return CheckResult(name, "FAIL", f"Missing: {install_hint}")
    return CheckResult(name, "PASS", found)


def _check_disk(path: Path, min_gb: int) -> CheckResult:
    try:
        usage = shutil.disk_usage(str(path))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < min_gb:
            return CheckResult("Disk", "WARNING", f"Low space on {path}: {free_gb:.1f} GB free")
        return CheckResult("Disk", "PASS", f"{path}: {free_gb:.1f} GB free")
    except FileNotFoundError:
        return CheckResult("Disk", "WARNING", f"Drive not found: {path}")


def _check_db() -> CheckResult:
    if not DB_PATH.exists():
        return CheckResult("Database", "WARNING", f"Missing: {DB_PATH}")
    try:
        temp = PROJECT_ROOT / f".db_write_test_{int(time.time())}.tmp"
        temp.write_text("test")
        temp.unlink()
        return CheckResult("Database", "PASS", f"Writable: {DB_PATH}")
    except Exception as exc:
        return CheckResult("Database", "FAIL", f"Not writable: {exc}")


def _check_chroma_storage() -> CheckResult:
    if not CHROMA_PATH.exists():
        return CheckResult("ChromaDB (local)", "FAIL", f"Missing: {CHROMA_PATH}")
    file_count = sum(1 for path in CHROMA_PATH.rglob("*") if path.is_file())
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        count = int(cursor.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] or 0)
        conn.close()
        if count <= 0:
            return CheckResult(
                "ChromaDB (local)",
                "WARNING",
                f"No embeddings indexed yet ({file_count} files on disk)",
            )
        return CheckResult(
            "ChromaDB (local)",
            "PASS",
            f"{count} embeddings indexed ({file_count} files on disk)",
        )
    except Exception as exc:
        if file_count == 0:
            return CheckResult("ChromaDB (local)", "WARNING", "chroma_storage is empty")
        return CheckResult(
            "ChromaDB (local)",
            "WARNING",
            f"Storage present but collection check failed: {exc} ({file_count} files on disk)",
        )


def _check_env() -> CheckResult:
    missing = [key for key in REQUIRED_ENV_KEYS if not os.getenv(key)]
    if missing:
        return CheckResult("Env", "WARNING", f"Missing keys: {', '.join(missing)}")
    return CheckResult("Env", "PASS", "Core env keys present")


# ---------------------------------------------------------------------------
# HTTP service checks
# ---------------------------------------------------------------------------

def _http_get(
    url: str,
    timeout: int = 4,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Return (status_code, error_string). status_code=0 means connection failed."""
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers=headers)
        return r.status_code, ""
    except Exception as exc:
        return 0, str(exc)


def _check_prowlarr() -> CheckResult:
    url = os.getenv("PROWLARR_URL", "http://localhost:9696")
    status, err = _http_get(f"{url}/health", timeout=4)
    if status == 200:
        return CheckResult("Prowlarr (T1)", "PASS", f"Live at {url}")
    if status == 401:
        return CheckResult("Prowlarr (T1)", "WARNING", f"Running but API key missing/wrong ({url})")
    if status == 0:
        return CheckResult("Prowlarr (T1)", "FAIL", f"Not reachable at {url} â€” run: docker-compose up -d")
    return CheckResult("Prowlarr (T1)", "WARNING", f"HTTP {status} from {url}")


def _check_rdtclient() -> CheckResult:
    url = "http://localhost:6500"
    status, err = _http_get(url, timeout=4)
    if status in (200, 301, 302, 303):
        return CheckResult("rdtclient (T1)", "PASS", f"Live at {url}")
    if status == 0:
        return CheckResult("rdtclient (T1)", "FAIL", f"Not reachable at {url} â€” run: docker-compose up -d")
    return CheckResult("rdtclient (T1)", "PASS", f"HTTP {status} at {url} (OK)")


def _check_slskd() -> CheckResult:
    url = os.getenv("LYRA_PROTOCOL_NODE_URL", "http://localhost:5030")
    status, err = _http_get(f"{url}/api/v0/application", timeout=4)
    if status in (200, 401):
        return CheckResult("slskd (T2)", "PASS", f"Live at {url}")
    if status == 0:
        return CheckResult("slskd (T2)", "FAIL", f"Not reachable at {url} â€” run: docker-compose up -d")
    return CheckResult("slskd (T2)", "WARNING", f"HTTP {status} from {url}")


def _check_llm() -> CheckResult:
    config = load_llm_config()
    diagnostics = diagnose_llm_config(config)
    provider_name = f"LLM ({config.provider_type})"
    if diagnostics.get("ok"):
        selected = diagnostics.get("selected_model") or config.model or config.fallback_model or "none"
        suffix = " via fallback" if diagnostics.get("fallback_used") else ""
        return CheckResult(provider_name, "PASS", f"Ready: {selected}{suffix}")
    status = "FAIL" if diagnostics.get("error_type") in {"provider_invalid", "model_missing"} else "WARNING"
    detail = diagnostics.get("error", "LLM unavailable")
    actions = diagnostics.get("actions") or []
    if actions:
        detail = f"{detail} | {actions[0]}"
    return CheckResult(provider_name, status, detail)

def _check_realdebrid() -> CheckResult:
    key = os.getenv("REAL_DEBRID_KEY") or os.getenv("REALDEBRID_API_KEY", "")
    if not key:
        return CheckResult("Real-Debrid API", "FAIL", "No API key in .env (REAL_DEBRID_KEY)")
    try:
        import requests
        r = requests.get(
            "https://api.real-debrid.com/rest/1.0/user",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            points = data.get("points", "?")
            expiry = data.get("expiration", "?")[:10]
            return CheckResult("Real-Debrid API", "PASS", f"Active â€” {points} pts, expires {expiry}")
        if r.status_code == 401:
            return CheckResult("Real-Debrid API", "FAIL", "Invalid API key â€” update REAL_DEBRID_KEY in .env")
        return CheckResult("Real-Debrid API", "WARNING", f"HTTP {r.status_code}")
    except Exception as exc:
        return CheckResult("Real-Debrid API", "WARNING", f"Could not reach API: {exc}")


def _check_lidarr() -> CheckResult:
    url = os.getenv("LIDARR_URL", "http://localhost:8686")
    key = os.getenv("LIDARR_API_KEY", "")
    if not key:
        return CheckResult("Lidarr (discovery)", "WARNING", "No API key (LIDARR_API_KEY)")
    status, err = _http_get(
        f"{url}/api/v1/system/status",
        timeout=4,
        headers={"X-Api-Key": key},
    )
    if status == 200:
        return CheckResult("Lidarr (discovery)", "PASS", f"Live at {url}")
    if status in (401, 403):
        return CheckResult("Lidarr (discovery)", "WARNING", f"Running but API key invalid ({url})")
    if status == 0:
        return CheckResult("Lidarr (discovery)", "FAIL", f"Not reachable at {url} -- run: docker-compose up -d")
    return CheckResult("Lidarr (discovery)", "WARNING", f"HTTP {status} from {url}")


def _check_spotdl() -> CheckResult:
    if shutil.which("spotdl"):
        return CheckResult("spotdl (T3)", "PASS", shutil.which("spotdl"))
    try:
        __import__("spotdl")
        return CheckResult("spotdl (T3)", "PASS", "Available (Python package)")
    except ImportError:
        return CheckResult("spotdl (T3)", "WARNING", "Not installed â€” pip install spotdl")


def _check_docker() -> CheckResult:
    if not shutil.which("docker"):
        return CheckResult("Docker", "WARNING", "docker CLI not found")
    try:
        import subprocess
        r = subprocess.run(["docker", "ps"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return CheckResult("Docker", "PASS", "Daemon running")
        return CheckResult("Docker", "WARNING", "Docker CLI found but daemon not running â€” launch Docker Desktop")
    except Exception as exc:
        return CheckResult("Docker", "WARNING", f"Docker check failed: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_doctor() -> List[CheckResult]:
    checks = [
        _check_python(),
        _check_tool("FFmpeg", "ffmpeg", "choco install ffmpeg  OR  winget install ffmpeg"),
        _check_tool("fpcalc", "fpcalc", "Install Chromaprint: https://acoustid.org/chromaprint"),
        _check_disk(Path("C:/"), 5),
        _check_disk(Path("A:/"), 10),
        _check_db(),
        _check_chroma_storage(),
        _check_env(),
        # Docker
        _check_docker(),
        # Acquisition tiers
        _check_realdebrid(),
        _check_prowlarr(),
        _check_rdtclient(),
        _check_slskd(),
        _check_spotdl(),
        # Discovery
        _check_lidarr(),
        # LLM
        _check_llm(),
    ]
    return checks


def _render(checks: List[CheckResult]) -> int:
    status_order = {"FAIL": 2, "WARNING": 1, "PASS": 0}
    overall = 0

    print()
    for check in checks:
        overall = max(overall, status_order.get(check.status, 0))
        icon = {"PASS": "[OK]", "WARNING": "[!!]", "FAIL": "[XX]"}.get(check.status, "[??]")
        print(f"  {icon} {check.name}: {check.details}")
    print()

    if overall == 0:
        print("Doctor result: ALL PASS")
        return 0
    if overall == 1:
        print("Doctor result: WARNINGS (system functional)")
        return 0
    print("Doctor result: FAILURES DETECTED")
    return 2


if __name__ == "__main__":
    load_dotenv(override=True)
    sys.exit(_render(run_doctor()))

