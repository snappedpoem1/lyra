"""Operational iteration runner and markdown reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import json
import os
import shutil
import subprocess
import sys

from oracle.config import PROJECT_ROOT


@dataclass
class StepResult:
    name: str
    ok: bool
    details: str


def _run_command(args: List[str], timeout: int = 900) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = (proc.stdout or "").strip()
        if proc.stderr:
            output = f"{output}\n{proc.stderr.strip()}".strip()
        return proc.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def _scope_environment() -> Dict[str, object]:
    keys = [
        "PROWLARR_URL",
        "PROWLARR_API_KEY",
        "REAL_DEBRID_KEY",
        "REAL_DEBRID_API_KEY",
        "QOBUZ_USERNAME",
        "QOBUZ_PASSWORD",
        "HF_TOKEN",
        "SLSKD_API_KEY",
        "LYRA_LLM_BASE_URL",
        "LYRA_LLM_MODEL",
        "LYRA_LM_STUDIO_EXE",
        "LYRA_ALLOW_GUARD_BYPASS",
        "LYRA_DB_PATH",
        "LIBRARY_BASE",
        "DOWNLOADS_FOLDER",
        "STAGING_FOLDER",
    ]
    env_state = {k: bool((os.getenv(k) or "").strip()) for k in keys}
    required = ["PROWLARR_API_KEY", "REAL_DEBRID_KEY", "LIBRARY_BASE"]
    missing_required = [k for k in required if not env_state.get(k)]
    return {
        "python": sys.version.split()[0],
        "cwd": str(PROJECT_ROOT),
        "tools": {
            "docker": bool(shutil.which("docker")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "fpcalc": bool(shutil.which("fpcalc")),
        },
        "env_present": env_state,
        "missing_required": missing_required,
    }


def _write_markdown_report(path: Path, payload: Dict[str, object]) -> None:
    lines: List[str] = []
    lines.append(f"# Lyra Ops Iteration Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Project: `{PROJECT_ROOT}`")
    lines.append("")

    lines.append("## Ordered Run")
    for s in payload.get("steps", []):
        if isinstance(s, dict):
            badge = "OK" if s.get("ok") else "FAIL"
            lines.append(f"- [{badge}] **{s.get('name')}**")
            details = str(s.get("details") or "").strip()
            if details:
                preview = details[:1200]
                lines.append("")
                lines.append("```text")
                lines.append(preview)
                lines.append("```")
    lines.append("")

    env_scope = payload.get("environment_scope", {})
    if isinstance(env_scope, dict):
        lines.append("## Environment Scope")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(env_scope, indent=2))
        lines.append("```")
        lines.append("")

    missing = payload.get("missing_pieces", [])
    lines.append("## Missing Pieces")
    if isinstance(missing, list) and missing:
        for item in missing:
            lines.append(f"- {item}")
    else:
        lines.append("- None detected by automated checks.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_iteration(
    *,
    bootstrap: bool = True,
    validate_apply: bool = False,
    validate_limit: int = 0,
    validate_workers: int = 0,
    validate_confidence: float = 0.7,
    drain_limit: int = 0,
    watch_once: bool = False,
    report_path: str | None = None,
) -> Dict[str, object]:
    """Run a practical operations sequence and write a markdown report."""
    steps: List[StepResult] = []

    if bootstrap:
        try:
            from oracle.bootstrap import bootstrap_runtime

            result = bootstrap_runtime(timeout_seconds=40)
            docker = result.get("docker", {})
            llm = result.get("llm", {})
            ok = bool(docker.get("ready"))
            details = (
                f"docker_ready={docker.get('ready')} docker_error={docker.get('error','')}\n"
                f"llm_ready={llm.get('ready')} llm_error={llm.get('error','')}\n"
                f"llm_model_boot_ok={llm.get('model_boot_ok')} "
                f"llm_model_boot_detail={llm.get('model_boot_detail','')}"
            )
            steps.append(StepResult("bootstrap_runtime", ok, details))
        except Exception as exc:
            steps.append(StepResult("bootstrap_runtime", False, str(exc)))

    ok, out = _run_command([sys.executable, "-m", "oracle.doctor"], timeout=180)
    steps.append(StepResult("doctor", ok, out))

    validate_cmd = [
        sys.executable,
        "-m",
        "oracle.cli",
        "validate",
        "--confidence",
        str(validate_confidence),
        "--workers",
        str(validate_workers),
    ]
    if validate_limit > 0:
        validate_cmd += ["--limit", str(validate_limit)]
    if validate_apply:
        validate_cmd += ["--apply"]
    ok, out = _run_command(validate_cmd, timeout=3600)
    steps.append(StepResult("validate", ok, out))

    if drain_limit > 0:
        ok, out = _run_command(
            [
                sys.executable,
                "-m",
                "oracle.cli",
                "drain",
                "--limit",
                str(drain_limit),
                "--workers",
                "0",
            ],
            timeout=3600,
        )
        steps.append(StepResult("drain", ok, out))
    else:
        steps.append(StepResult("drain", True, "Skipped (drain_limit=0)"))

    if watch_once:
        ok, out = _run_command([sys.executable, "-m", "oracle.cli", "watch", "--once"], timeout=3600)
        steps.append(StepResult("watch_once", ok, out))
    else:
        steps.append(StepResult("watch_once", True, "Skipped (watch_once=False)"))

    ok, out = _run_command([sys.executable, "-m", "oracle.cli", "status"], timeout=180)
    steps.append(StepResult("status", ok, out))
    ok, out = _run_command([sys.executable, "-m", "oracle.cli", "audit"], timeout=300)
    steps.append(StepResult("audit", ok, out))

    env_scope = _scope_environment()
    missing_pieces: List[str] = []
    if isinstance(env_scope, dict):
        for req in env_scope.get("missing_required", []):
            missing_pieces.append(f"Missing required env key: {req}")

    doctor_step = next((s for s in steps if s.name == "doctor"), None)
    if doctor_step and "LM Studio (LLM): Offline" in doctor_step.details:
        missing_pieces.append("LM Studio is offline; LLM-enhanced paths remain disabled.")
    status_step = next((s for s in steps if s.name == "status"), None)
    if status_step and "Queue (pending):" in status_step.details:
        pass

    if not report_path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = str(PROJECT_ROOT / "Reports" / f"ops_iteration_{stamp}.md")
    report_file = Path(report_path)

    payload = {
        "steps": [s.__dict__ for s in steps],
        "environment_scope": env_scope,
        "missing_pieces": missing_pieces,
        "report_path": str(report_file),
    }
    _write_markdown_report(report_file, payload)
    return payload
