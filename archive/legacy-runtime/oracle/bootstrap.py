"""Best-effort startup bootstrap for local dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from oracle.config import PROJECT_ROOT, get_llm_settings


def _http_ready(url: str, timeout: float = 3.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return True
        if r.status_code in (401, 403):
            return True
    except Exception:
        return False
    return False


def _llm_probe_url(base_url: str) -> str:
    base = (base_url or "http://127.0.0.1:1234/v1").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _common_lmstudio_paths() -> list[Path]:
    candidates: list[Path] = []
    env_vars = [
        os.getenv("LYRA_LM_STUDIO_EXE", "").strip(),
        os.getenv("LM_STUDIO_EXE", "").strip(),
    ]
    for value in env_vars:
        if value:
            candidates.append(Path(value))

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
    candidates.extend(
        [
            local / "Programs" / "LM Studio" / "LM Studio.exe",
            local / "LM-Studio" / "LM Studio.exe",
            program_files / "LM Studio" / "LM Studio.exe",
            program_files / "AMD" / "AI_Bundle" / "LMStudio" / "LM Studio" / "LM Studio.exe",
        ]
    )
    return candidates


def _find_lmstudio_exe() -> Path | None:
    for path in _common_lmstudio_paths():
        if path and path.exists():
            return path
    return None


def _common_lms_cli_paths(exe_path: Path | None) -> list[Path]:
    candidates: list[Path] = []
    env_vars = [
        os.getenv("LYRA_LMS_CLI_EXE", "").strip(),
        os.getenv("LMS_CLI_EXE", "").strip(),
    ]
    for value in env_vars:
        if value:
            candidates.append(Path(value))

    which_lms = shutil.which("lms")
    if which_lms:
        candidates.append(Path(which_lms))

    user_profile = Path(os.environ.get("USERPROFILE", ""))
    if str(user_profile):
        candidates.append(user_profile / ".lmstudio" / "bin" / "lms.exe")

    # CLI bundled with the selected LM Studio install.
    if exe_path:
        candidates.append(exe_path.parent / "resources" / "app" / ".webpack" / "lms.exe")

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
    candidates.extend(
        [
            local / "Programs" / "LM Studio" / "resources" / "app" / ".webpack" / "lms.exe",
            local / "LM-Studio" / "resources" / "app" / ".webpack" / "lms.exe",
            program_files / "LM Studio" / "resources" / "app" / ".webpack" / "lms.exe",
        ]
    )
    return candidates


def _find_lms_cli(exe_path: Path | None) -> Path | None:
    for path in _common_lms_cli_paths(exe_path):
        if path and path.exists():
            return path
    return None


def _run_lms(
    cli_path: Path, args: list[str], timeout: int, *, interactive: bool = False
) -> tuple[bool, str]:
    try:
        if interactive and os.name == "nt":
            return _run_lms_interactive(cli_path, args, timeout)
        proc = subprocess.run(
            [str(cli_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return proc.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


def _spawn_lms_server(cli_path: Path, host: str, port: int) -> tuple[bool, str]:
    args = [str(cli_path), "server", "start", "--port", str(port), "--bind", host]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(
            args,
            cwd=str(cli_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=os.name != "nt",
        )
        return True, "spawned detached lms server start"
    except Exception as exc:
        return False, f"detached launch failed: {exc}"


_TASK_NAME = "LyraOracleLMSBoot"


def _run_lms_interactive(cli_path: Path, args: list[str], timeout: int) -> tuple[bool, str]:
    """Run an lms command via a Windows scheduled task so it executes in the
    interactive desktop session.  This is required because ``lms server start``
    needs to wake the LM Studio Electron app, which only works from a proper
    interactive context — not from a subprocess spawned by a headless tool."""
    bat = cli_path.parent / "lyra_server_start.bat"
    try:
        cmd_line = f'"{cli_path}" {" ".join(args)}'
        bat.write_text(f"@echo off\n{cmd_line}\n", encoding="utf-8")

        # Create (overwrite) the scheduled task.
        subprocess.run(
            ["schtasks", "/Create", "/TN", _TASK_NAME, "/TR", str(bat),
             "/SC", "ONCE", "/ST", "00:00", "/F"],
            capture_output=True, text=True, timeout=10,
        )
        # Fire it.
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", _TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, f"schtasks /Run failed: {result.stderr.strip()}"

        # Poll until the task completes or we run out of time.
        deadline = time.time() + max(8, timeout)
        while time.time() < deadline:
            time.sleep(2)
            # Check if the task has completed (success or failure).
            info = subprocess.run(
                ["schtasks", "/Query", "/TN", _TASK_NAME, "/FO", "LIST"],
                capture_output=True, text=True, timeout=5,
            )
            info_text = info.stdout or ""
            if "Running" not in info_text:
                # Task finished.  Check if server is up via lms server status.
                ok2, out2 = _run_lms(cli_path, ["server", "status"], timeout=5)
                if "running" in out2.lower() and "not running" not in out2.lower():
                    return True, "server started via scheduled task"
                return False, f"task completed but server not running: {out2[:200]}"

        return False, "timed out waiting for scheduled task"
    except Exception as exc:
        return False, f"interactive launch failed: {exc}"
    finally:
        # Best-effort cleanup of the task and bat file.
        try:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", _TASK_NAME, "/F"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        try:
            bat.unlink(missing_ok=True)
        except Exception:
            pass


def _daemon_running(lms_cli: Path, timeout: int = 5) -> bool:
    ok, out = _run_lms(lms_cli, ["daemon", "status"], timeout=timeout)
    lower = out.lower()
    # "LM Studio is not running" contains "running" — must exclude negatives.
    if ok and "running" in lower and "not running" not in lower:
        return True
    return False


def _llm_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or "127.0.0.1"
    if host.lower() == "localhost":
        host = "127.0.0.1"
    port = int(parsed.port or 1234)
    return host, port


def _model_autoload_enabled() -> bool:
    return os.getenv("LYRA_LM_AUTOLOAD", "1").strip().lower() in {"1", "true", "yes", "on"}


def _is_model_loaded(lms_cli: Path, model: str, timeout: int = 6) -> bool:
    if not model:
        return False
    ok, out = _run_lms(lms_cli, ["ps"], timeout=timeout)
    if not ok:
        return False
    return model.lower() in out.lower()


def _ensure_model_loaded(lms_cli: Path | None, model: str, timeout_seconds: int) -> tuple[bool, str]:
    if not model:
        return True, "no model configured"
    if not lms_cli:
        return False, "lms CLI not found for model load"
    if _is_model_loaded(lms_cli, model, timeout=6):
        return True, f"already loaded: {model}"
    load_timeout = max(8, min(40, int(timeout_seconds)))
    ok, out = _run_lms(lms_cli, ["load", model], timeout=load_timeout)
    if not ok:
        return False, f"load failed: {out[:240]}"
    if _is_model_loaded(lms_cli, model, timeout=8):
        return True, f"loaded: {model}"
    return False, f"load command returned but model not in lms ps: {model}"


def ensure_lmstudio(timeout_seconds: int = 30) -> dict:
    settings = get_llm_settings()
    base_url = settings.get("base_url", "http://127.0.0.1:1234/v1")
    probe_url = _llm_probe_url(base_url)

    exe_path = _find_lmstudio_exe()
    lms_cli = _find_lms_cli(exe_path)
    model = (settings.get("model") or "").strip()
    autoload_enabled = _model_autoload_enabled()

    if _http_ready(probe_url):
        if autoload_enabled and model:
            loaded_ok, loaded_detail = _ensure_model_loaded(
                lms_cli, model, timeout_seconds=max(8, int(timeout_seconds // 2))
            )
            return {
                "ready": True,
                "started": False,
                "probe_url": probe_url,
                "model_boot_ok": loaded_ok,
                "model_boot_detail": loaded_detail,
            }
        return {"ready": True, "started": False, "probe_url": probe_url}

    # Preferred path: detached `lms server start`, then readiness poll.
    if lms_cli:
        host, port = _llm_host_port(base_url)
        notes: list[str] = []
        total_budget = max(10, int(timeout_seconds))
        phase_timeout = max(10, min(20, total_budget // 3))

        status_ok, status_out = _run_lms(lms_cli, ["server", "status"], timeout=6)
        notes.append(f"server_status_ok={status_ok} detail={status_out[:220]}")

        ok, out = _spawn_lms_server(lms_cli, host, port)
        notes.append(f"server_start_ok={ok} detail={out[:220]}")

        if ok:
            model_boot_ok: bool | None = None
            model_boot_detail = ""
            if autoload_enabled and model:
                if _http_ready(probe_url, timeout=2.5):
                    model_boot_ok, model_boot_detail = _ensure_model_loaded(
                        lms_cli, model, timeout_seconds=max(6, phase_timeout)
                    )
                    notes.append(
                        f"model_load_ok={model_boot_ok} model={model} detail={model_boot_detail[:220]}"
                    )
                else:
                    model_boot_detail = "deferred_until_server_ready"
                    notes.append(f"model_load_deferred=model_server_not_ready model={model}")

            # Brief poll in case server needs a moment after start.
            deadline = time.time() + total_budget
            while time.time() < deadline:
                if _http_ready(probe_url):
                    payload = {
                        "ready": True,
                        "started": True,
                        "probe_url": probe_url,
                        "lms_cli": str(lms_cli),
                        "method": "lms_cli",
                    }
                    if autoload_enabled and model:
                        if model_boot_ok is None:
                            model_boot_ok, model_boot_detail = _ensure_model_loaded(
                                lms_cli, model, timeout_seconds=max(6, phase_timeout)
                            )
                        payload["model_boot_ok"] = model_boot_ok
                        payload["model_boot_detail"] = model_boot_detail
                    return payload
                time.sleep(1.5)

            # server start succeeded but API not yet responding — still report success
            if ok:
                return {
                    "ready": _http_ready(probe_url, timeout=3),
                    "started": True,
                    "probe_url": probe_url,
                    "lms_cli": str(lms_cli),
                    "method": "lms_cli",
                    "notes": " | ".join(notes),
                }

        cli_error = " | ".join(notes)
    else:
        cli_error = "lms CLI not found"

    # Fallback path: start LM Studio desktop app.
    if not exe_path:
        return {
            "ready": False,
            "started": False,
            "probe_url": probe_url,
            "error": f"{cli_error}; LM Studio executable not found",
        }

    try:
        # Launch with the install folder as cwd for Electron bundles that
        # require relative app resources.
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(exe_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {
            "ready": False,
            "started": False,
            "probe_url": probe_url,
            "error": f"{cli_error}; Failed to launch LM Studio: {exc}",
        }

    deadline = time.time() + max(12, int(timeout_seconds))
    while time.time() < deadline:
        if _http_ready(probe_url):
            return {"ready": True, "started": True, "probe_url": probe_url, "exe": str(exe_path)}
        time.sleep(1.5)

    return {
        "ready": False,
        "started": True,
        "probe_url": probe_url,
        "exe": str(exe_path),
        "error": f"{cli_error}; LM Studio did not become ready before timeout",
    }


def ensure_docker_services(
    services: list[str] | None = None,
    timeout_seconds: int = 40,
) -> dict:
    if services is None:
        # Keep startup fast/reliable by default; Qobuz sidecar can be opt-in.
        services = ["prowlarr", "rdtclient", "slskd"]
        include_qobuz = os.getenv("LYRA_BOOTSTRAP_QOBUZ", "").strip().lower() in {"1", "true", "yes", "on"}
        if include_qobuz:
            services.append("qobuz")
    compose_file = Path(PROJECT_ROOT) / "docker-compose.yml"
    if not compose_file.exists():
        return {"ready": False, "started": False, "error": f"Compose file missing: {compose_file}"}

    if not shutil.which("docker"):
        return {"ready": False, "started": False, "error": "docker CLI not found"}

    try:
        check = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=8)
        if check.returncode != 0:
            return {"ready": False, "started": False, "error": "Docker daemon not available"}
    except Exception as exc:
        return {"ready": False, "started": False, "error": f"Docker check failed: {exc}"}

    # Short-circuit when target services are already live.
    service_health_urls = {
        "prowlarr": "http://localhost:9696/health",
        "rdtclient": "http://localhost:6500",
        "slskd": "http://localhost:5030/api/v0/application",
        "qobuz": "http://localhost:7700/health",
    }
    urls = [service_health_urls[s] for s in services if s in service_health_urls]
    if urls and all(_http_ready(u) for u in urls):
        return {"ready": True, "started": False, "detail": "services already running"}

    cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d", *services]
    try:
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout_seconds)
        ok = proc.returncode == 0
        if not ok and urls and all(_http_ready(u) for u in urls):
            # Some environments have pre-existing named containers not attached to this compose project.
            return {
                "ready": True,
                "started": False,
                "detail": "services already live (compose returned non-zero)",
                "warning": proc.stderr.strip() or proc.stdout.strip(),
            }
        return {
            "ready": ok,
            "started": ok,
            "error": "" if ok else (proc.stderr.strip() or proc.stdout.strip() or "compose up failed"),
        }
    except Exception as exc:
        return {"ready": False, "started": False, "error": f"docker compose failed: {exc}"}


def _should_bootstrap_legacy_services() -> bool:
    """Return True only when legacy external-service bootstrap is explicitly enabled."""
    return os.getenv("LYRA_BOOTSTRAP_LEGACY_SERVICES", "0").strip().lower() in {"1", "true", "yes", "on"}


def bootstrap_runtime(timeout_seconds: int = 40) -> dict:
    """Best-effort bootstrap for dependencies before app starts."""
    if _should_bootstrap_legacy_services():
        external_services = ensure_docker_services(timeout_seconds=timeout_seconds)
    else:
        external_services = {
            "ready": False,
            "started": False,
            "skipped": True,
            "legacy_layer": True,
            "error": "Legacy external-service bootstrap disabled by architecture policy",
        }
    llm = ensure_lmstudio(timeout_seconds=timeout_seconds)
    return {"external_services": external_services, "llm": llm}
