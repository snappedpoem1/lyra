#!/usr/bin/env python3
"""Run a repeatable backend stability cycle.

Sequence:
1) LLM second-pass verification (cold-start capable, unload on completion)
2) DB/API local QA checks
3) Pytest regression suite
4) JSON report persisted to Reports/
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "Reports"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_llm_usage.py"
QA_SCRIPT = ROOT / "scripts" / "run_local_qa.py"
SURFACE_AUDIT_SCRIPT = ROOT / "scripts" / "run_backend_surface_audit.py"


@dataclass
class StepResult:
    name: str
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_step(name: str, command: List[str], cwd: Path) -> StepResult:
    start = datetime.now(UTC)
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    end = datetime.now(UTC)
    return StepResult(
        name=name,
        command=command,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_sec=(end - start).total_seconds(),
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run repeatable Lyra backend stability cycle.")
    p.add_argument("--skip-llm", action="store_true", help="Skip LLM verification step.")
    p.add_argument("--llm-provider", default="ollama", help="Provider for LLM verify step.")
    p.add_argument("--llm-base-url", default="http://localhost:11434/v1", help="Base URL for LLM verify step.")
    p.add_argument("--llm-model", default="oracle-brain:latest", help="Model for LLM verify step.")
    p.add_argument("--llm-timeout", type=int, default=60, help="Timeout seconds for LLM calls.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    results: List[StepResult] = []

    if not args.skip_llm:
        llm_cmd = [
            py,
            str(VERIFY_SCRIPT),
            "--provider",
            args.llm_provider,
            "--base-url",
            args.llm_base_url,
            "--model",
            args.llm_model,
            "--timeout-seconds",
            str(max(1, args.llm_timeout)),
            "--control-check",
            "--shutdown",
        ]
        results.append(run_step("llm_verify", llm_cmd, ROOT))
        if not results[-1].ok:
            print("[FAIL] llm_verify")
            print(results[-1].stdout)
            print(results[-1].stderr)

    qa_cmd = [py, str(QA_SCRIPT)]
    results.append(run_step("local_qa", qa_cmd, ROOT))
    if not results[-1].ok:
        print("[FAIL] local_qa")
        print(results[-1].stdout)
        print(results[-1].stderr)

    surface_cmd = [py, str(SURFACE_AUDIT_SCRIPT)]
    results.append(run_step("backend_surface_audit", surface_cmd, ROOT))
    if not results[-1].ok:
        print("[FAIL] backend_surface_audit")
        print(results[-1].stdout)
        print(results[-1].stderr)

    pytest_cmd = [py, "-m", "pytest", "-q"]
    results.append(run_step("pytest", pytest_cmd, ROOT))
    if not results[-1].ok:
        print("[FAIL] pytest")
        print(results[-1].stdout)
        print(results[-1].stderr)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"stability_cycle_{ts}.json"
    latest_path = REPORTS_DIR / "stability_cycle_latest.json"

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(ROOT),
        "steps": [
            {
                "name": r.name,
                "ok": r.ok,
                "returncode": r.returncode,
                "duration_sec": r.duration_sec,
                "command": r.command,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }
            for r in results
        ],
        "all_ok": all(r.ok for r in results),
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"[INFO] report: {report_path}")
    print(f"[INFO] latest: {latest_path}")
    print(f"[INFO] overall: {'PASS' if payload['all_ok'] else 'FAIL'}")
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
