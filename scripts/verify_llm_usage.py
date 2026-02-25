#!/usr/bin/env python3
"""Verify that LLM-assisted classification is actually invoked and audited.

This script targets the ambiguous-track path used by classifier second-pass logic:
regex result == "original" with confidence <= 0.5.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "lyra_registry.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _choose_limit(sample_window: int, target_ambiguous: int) -> tuple[int, int]:
    from oracle.classifier import classify_track

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    track_ids = [
        row[0]
        for row in cur.execute(
            "SELECT track_id FROM tracks ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC LIMIT ?",
            (sample_window,),
        ).fetchall()
    ]
    con.close()

    ambiguous_positions: list[int] = []
    for pos, track_id in enumerate(track_ids, start=1):
        result = classify_track(track_id)
        if (
            result.get("version_type") == "original"
            and float(result.get("confidence", 0.0)) <= 0.5
        ):
            ambiguous_positions.append(pos)
        if len(ambiguous_positions) >= target_ambiguous:
            break

    if not ambiguous_positions:
        return min(sample_window, max(1, target_ambiguous * 25)), 0
    return ambiguous_positions[min(target_ambiguous, len(ambiguous_positions)) - 1], len(ambiguous_positions)


def _audit_count() -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    value = cur.execute("SELECT COUNT(*) FROM llm_audit").fetchone()[0]
    con.close()
    return int(value)


def _last_audit_rows(limit: int = 5) -> list[tuple[Any, ...]]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT track_id, regex_version_type, llm_version_type, llm_confidence, llm_ok, llm_applied, llm_error
        FROM llm_audit
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    con.close()
    return rows


def _call_classify(limit: int, use_llm: bool) -> tuple[int, dict]:
    import lyra_api

    client = lyra_api.app.test_client()
    payload = {"limit": int(limit), "use_llm": bool(use_llm)}

    # Keep output focused on verification results.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        resp = client.post("/api/curate/classify", json=payload)
    body = resp.get_json(silent=True)
    return resp.status_code, body if isinstance(body, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify LLM usage path for classify second-pass.")
    parser.add_argument("--provider", default="", help="Override LYRA_LLM_PROVIDER for this run.")
    parser.add_argument("--base-url", default="", help="Override LYRA_LLM_BASE_URL for this run.")
    parser.add_argument("--model", default="", help="Override LYRA_LLM_MODEL for this run.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="LYRA_LLM_TIMEOUT_SECONDS override.")
    parser.add_argument("--sample-window", type=int, default=250, help="Tracks sampled to find ambiguous candidates.")
    parser.add_argument("--target-ambiguous", type=int, default=3, help="Target count of ambiguous tracks in classify limit.")
    parser.add_argument("--control-check", action="store_true", help="Also run use_llm=false control and verify no audit growth.")
    parser.add_argument(
        "--shutdown",
        action="store_true",
        help="After verification, unload the active Ollama model (for cold-start repeatability).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_provider = args.provider.strip().lower() if args.provider else ""
    selected_model = args.model.strip()

    if not DB_PATH.exists():
        print(f"[FAIL] DB missing: {DB_PATH}")
        return 1

    if args.provider:
        os.environ["LYRA_LLM_PROVIDER"] = args.provider
    if args.base_url:
        os.environ["LYRA_LLM_BASE_URL"] = args.base_url
    if args.model:
        os.environ["LYRA_LLM_MODEL"] = args.model
    os.environ["LYRA_LLM_TIMEOUT_SECONDS"] = str(max(1, args.timeout_seconds))

    limit, ambiguous_found = _choose_limit(
        sample_window=max(10, args.sample_window),
        target_ambiguous=max(1, args.target_ambiguous),
    )

    before = _audit_count()
    t0 = time.time()
    status, summary = _call_classify(limit=limit, use_llm=True)
    elapsed = time.time() - t0
    after = _audit_count()
    delta = after - before

    llm_checked = int(summary.get("llm_checked", 0))
    llm_errors = int(summary.get("llm_errors", 0))
    llm_suggested = int(summary.get("llm_suggested", 0))
    llm_applied = int(summary.get("llm_applied", 0))

    print("== LLM Usage Verification ==")
    print(f"chosen_limit={limit}")
    print(f"ambiguous_found_in_window={ambiguous_found}")
    print(f"api_status={status}")
    print(f"elapsed_sec={elapsed:.2f}")
    print(f"summary={summary}")
    print(f"audit_before={before}")
    print(f"audit_after={after}")
    print(f"audit_delta={delta}")
    print(f"latest_audit_rows={_last_audit_rows(5)}")

    if status != 200:
        print("[FAIL] classify endpoint did not return HTTP 200")
        return 1
    if llm_checked <= 0:
        print("[FAIL] LLM second-pass was not triggered (llm_checked=0)")
        return 1
    if delta <= 0:
        print("[FAIL] llm_audit did not record any rows")
        return 1

    if args.control_check:
        control_before = _audit_count()
        c_status, c_summary = _call_classify(limit=limit, use_llm=False)
        control_after = _audit_count()
        control_delta = control_after - control_before
        print("== Control Check (use_llm=false) ==")
        print(f"api_status={c_status}")
        print(f"summary={c_summary}")
        print(f"audit_delta={control_delta}")
        if c_status != 200 or control_delta != 0:
            print("[FAIL] control check failed (unexpected audit writes when use_llm=false)")
            return 1

    print(
        "[PASS] LLM second-pass path is active "
        f"(checked={llm_checked}, errors={llm_errors}, suggested={llm_suggested}, applied={llm_applied})"
    )

    if args.shutdown:
        provider = selected_provider or os.environ.get("LYRA_LLM_PROVIDER", "").strip().lower()
        model = selected_model or os.environ.get("LYRA_LLM_MODEL", "").strip()
        if provider == "ollama" and model:
            try:
                stop = subprocess.run(
                    ["ollama", "stop", model],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if stop.returncode == 0:
                    print(f"[INFO] Unloaded Ollama model: {model}")
                else:
                    details = (stop.stderr or stop.stdout or "").strip()
                    print(f"[WARN] Could not unload Ollama model {model}: {details}")
            except Exception as exc:
                print(f"[WARN] Ollama shutdown failed: {exc}")
        else:
            print("[INFO] Shutdown skipped (provider is not ollama or model not set).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
