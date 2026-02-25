#!/usr/bin/env python3
"""Verify both local LLM backends (LM Studio + Ollama) can boot and answer a ping."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "Reports"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle.llm import LLMClient


@dataclass
class BackendResult:
    backend: str
    ok: bool
    base_url: str
    model: str = ""
    detail: str = ""
    models: list[str] | None = None


def _wait_http(url: str, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3):  # nosec - local loopback only
                return True
        except Exception:
            time.sleep(1.0)
    return False


def _fetch_models(base_url: str) -> list[str]:
    try:
        with urlopen(base_url.rstrip("/") + "/models", timeout=5) as resp:  # nosec - local loopback only
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        items = data.get("data", [])
        return [str(item.get("id")) for item in items if item.get("id")]
    except Exception:
        return []


def _llm_ping(provider: str, base_url: str, model: str) -> tuple[bool, str]:
    os.environ["LYRA_LLM_PROVIDER"] = provider
    os.environ["LYRA_LLM_BASE_URL"] = base_url
    os.environ["LYRA_LLM_MODEL"] = model
    os.environ["LYRA_LLM_TIMEOUT_SECONDS"] = "20"
    client = LLMClient.from_env()
    status = client.check_available(probe=False)
    if not status.ok:
        return False, status.error
    result = client.chat(
        [{"role": "user", "content": "Reply exactly with: ok"}],
        temperature=0.0,
        max_tokens=8,
    )
    if not result.get("ok"):
        return False, str(result.get("error", "chat failed"))
    return True, (result.get("text") or "").strip()


def verify_ollama(preferred_model: str = "") -> BackendResult:
    base_url = "http://127.0.0.1:11434/v1"
    models_url = base_url + "/models"
    if not _wait_http(models_url, timeout_seconds=4):
        if shutil.which("ollama") is None:
            return BackendResult("ollama", False, base_url, detail="ollama command not found")
        try:
            subprocess.Popen(  # noqa: S603,S607 - local trusted binary
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            return BackendResult("ollama", False, base_url, detail=f"failed to start ollama serve: {exc}")
        if not _wait_http(models_url, timeout_seconds=25):
            return BackendResult("ollama", False, base_url, detail="Ollama API not reachable")

    models = _fetch_models(base_url)
    if not models:
        return BackendResult("ollama", False, base_url, detail="no models available", models=models)
    model = preferred_model or os.environ.get("LYRA_OLLAMA_MODEL", "").strip() or models[0]
    ok, detail = _llm_ping("ollama", base_url, model)
    try:
        subprocess.run(["ollama", "stop", model], check=False, capture_output=True, text=True)  # noqa: S603,S607
    except Exception:
        pass
    return BackendResult("ollama", ok, base_url, model=model, detail=detail, models=models)


def _run_lms(args: list[str], timeout_seconds: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603,S607 - local trusted binary
        ["lms", *args],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _lmstudio_app_path() -> Path:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    return local_appdata / "Programs" / "LM Studio" / "LM Studio.exe"


def _lmstudio_main_log_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", ""))
    return appdata / "LM Studio" / "logs" / "main.log"


def _tail_log(path: Path, lines: int = 40) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _ensure_lmstudio_local_service_enabled() -> str:
    settings_path = Path.home() / ".lmstudio" / "settings.json"
    if not settings_path.exists():
        return ""
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    changed = False
    if data.get("enableLocalService") is not True:
        data["enableLocalService"] = True
        changed = True
    if data.get("cliInstalled") is not True:
        data["cliInstalled"] = True
        changed = True
    if changed:
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return "updated ~/.lmstudio/settings.json (enableLocalService=true, cliInstalled=true)"
    return ""


def _launch_lmstudio_app() -> tuple[bool, str]:
    app = _lmstudio_app_path()
    if not app.exists():
        return False, f"LM Studio.exe not found at {app}"
    try:
        subprocess.Popen(  # noqa: S603,S607 - local trusted binary
            [str(app), "--headless"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, f"launched {app}"
    except Exception as exc:
        return False, f"failed launching LM Studio.exe: {exc}"


def _lmstudio_disk_models() -> list[str]:
    cp = _run_lms(["ls", "--json"], timeout_seconds=60)
    if cp.returncode != 0:
        return []
    try:
        parsed: Any = json.loads(cp.stdout)
    except Exception:
        return []
    names: list[str] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                for key in ("key", "modelKey", "id"):
                    if item.get(key):
                        names.append(str(item[key]))
                        break
    elif isinstance(parsed, dict) and isinstance(parsed.get("models"), list):
        for item in parsed["models"]:
            if isinstance(item, dict):
                for key in ("key", "modelKey", "id"):
                    if item.get(key):
                        names.append(str(item[key]))
                        break
    return list(dict.fromkeys(names))


def verify_lmstudio(preferred_model: str = "") -> BackendResult:
    base_url = "http://127.0.0.1:1234/v1"
    models_url = base_url + "/models"

    status_cp = _run_lms(["server", "status"], timeout_seconds=15)
    status_text = (status_cp.stdout + status_cp.stderr).strip().lower()
    running = "is running" in status_text
    remediation_notes: list[str] = []
    note = _ensure_lmstudio_local_service_enabled()
    if note:
        remediation_notes.append(note)

    if not running:
        start_cp = _run_lms(["server", "start"], timeout_seconds=120)
        if start_cp.returncode != 0:
            started_app, app_note = _launch_lmstudio_app()
            remediation_notes.append(app_note)
            if started_app and _wait_http(models_url, timeout_seconds=45):
                running = True
            else:
                tail = _tail_log(_lmstudio_main_log_path(), lines=30)
                detail = (start_cp.stdout + "\n" + start_cp.stderr).strip() or "failed to start LM Studio server"
                if tail:
                    detail += f"\nLM Studio main.log tail:\n{tail}"
                if remediation_notes:
                    detail += "\nRemediation attempted: " + " | ".join(remediation_notes)
                return BackendResult("lmstudio", False, base_url, detail=detail)

    if not _wait_http(models_url, timeout_seconds=20):
        tail = _tail_log(_lmstudio_main_log_path(), lines=30)
        detail = "LM Studio API not reachable"
        if tail:
            detail += f"\nLM Studio main.log tail:\n{tail}"
        if remediation_notes:
            detail += "\nRemediation attempted: " + " | ".join(remediation_notes)
        return BackendResult("lmstudio", False, base_url, detail=detail)

    models = _fetch_models(base_url)
    model = preferred_model or os.environ.get("LYRA_LMSTUDIO_MODEL", "").strip() or os.environ.get("LYRA_LLM_MODEL", "").strip()
    if model and model not in models:
        load_cp = _run_lms(["load", "--yes", model], timeout_seconds=180)
        if load_cp.returncode != 0:
            detail = (load_cp.stdout + "\n" + load_cp.stderr).strip() or f"failed to load model {model}"
            return BackendResult("lmstudio", False, base_url, model=model, detail=detail, models=models)
        time.sleep(2.0)
        models = _fetch_models(base_url)
    if not models:
        disk_models = _lmstudio_disk_models()
        if disk_models:
            model = model or disk_models[0]
            load_cp = _run_lms(["load", "--yes", model], timeout_seconds=180)
            if load_cp.returncode == 0:
                time.sleep(2.0)
                models = _fetch_models(base_url)
        if not models:
            return BackendResult("lmstudio", False, base_url, detail="LM Studio API reachable but no loaded model", models=models)

    if not model:
        model = models[0]
    ok, detail = _llm_ping("lmstudio", base_url, model)
    if remediation_notes:
        detail = f"{detail} | remediation: {' | '.join(remediation_notes)}"
    return BackendResult("lmstudio", ok, base_url, model=model, detail=detail, models=models)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify LM Studio and Ollama boot + ping.")
    p.add_argument("--lmstudio-model", default="", help="Preferred LM Studio model id/key.")
    p.add_argument("--ollama-model", default="", help="Preferred Ollama model id.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)

    results = [
        verify_lmstudio(preferred_model=args.lmstudio_model.strip()),
        verify_ollama(preferred_model=args.ollama_model.strip()),
    ]

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "results": [asdict(r) for r in results],
        "ok": all(r.ok for r in results),
    }

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out = REPORTS / f"llm_backend_boot_{stamp}.json"
    latest = REPORTS / "llm_backend_boot_latest.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.backend} model={r.model or '-'} detail={r.detail}")
    print(f"[INFO] report={out}")
    print(f"[INFO] latest={latest}")
    print(f"[INFO] overall={'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
