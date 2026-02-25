#!/usr/bin/env python3
"""Run backend surface audit: imports, doc endpoint coverage, API non-500 smoke."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "Reports"
PLAN_DOC = ROOT / "plans" / "web_ui_implementation_plan.md"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class EndpointResult:
    method: str
    path: str
    status: int
    body: Any


def _collect_doc_endpoints() -> list[str]:
    text = PLAN_DOC.read_text(encoding="utf-8", errors="ignore")
    return sorted(set(re.findall(r"`(/api/[^`]+)`", text)))


def _collect_app_routes(app) -> list[str]:
    return sorted(r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/api/"))


def _import_sweep() -> list[dict[str, str]]:
    mods = sorted(
        {
            ".".join(p.relative_to(ROOT).with_suffix("").parts)
            for p in (ROOT / "oracle").rglob("*.py")
            if "__pycache__" not in p.parts
        }
    )
    failures: list[dict[str, str]] = []
    for mod in mods:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            failures.append({"module": mod, "error": str(exc)})
    return failures


def _smoke_cases(track_id: str) -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", "/api/health", None),
        ("GET", "/api/status", None),
        ("GET", "/api/cache/stats", None),
        ("POST", "/api/search", {"query": "metal", "n": 5}),
        ("POST", "/api/search/rewrite", {"query": "warm indie nostalgia"}),
        ("POST", "/api/search/hybrid", {"query": "warm indie nostalgia", "n": 5}),
        ("POST", "/api/library/validate", {"limit": 3}),
        ("GET", "/api/library/tracks?limit=5", None),
        ("GET", "/api/vibes", None),
        ("POST", "/api/vibes/generate", {"prompt": "test vibe", "n": 5}),
        ("POST", "/api/vibes/create", {"prompt": "test vibe", "name": "audit vibe", "n": 5, "build": False, "materialize": False}),
        ("POST", "/api/vibes/save", {"name": "audit save", "query": "indie warm", "n": 5}),
        ("POST", "/api/vibes/build", {"name": "audit save"}),
        ("POST", "/api/vibes/narrate", {"name": "audit save"}),
        ("POST", "/api/vibes/refresh", {"name": "audit save"}),
        ("POST", "/api/vibes/delete", {"name": "audit save"}),
        ("POST", "/api/curate/classify", {"limit": 5, "use_llm": False}),
        ("POST", "/api/curate/plan", {"target": "library", "limit": 5}),
        ("POST", "/api/curate/apply", {"plan": []}),
        ("GET", "/api/acquire/queue", None),
        ("POST", "/api/acquire/process", {"limit": 1}),
        ("GET", "/api/downloads", None),
        ("POST", "/api/downloads/organize", {"dry_run": True}),
        ("GET", "/api/spotify/missing", None),
        ("GET", "/api/spotify/stats", None),
        ("POST", "/api/scout/cross-genre", {"source_genre": "metalcore", "target_genre": "jazz", "n": 5}),
        ("POST", "/api/lore/trace", {"artist": "Deftones", "hops": 1, "topk": 5}),
        ("GET", "/api/lore/connections?artist=Deftones&hops=1&topk=5", None),
        ("GET", f"/api/dna/trace?track_id={track_id}", None),
        ("GET", f"/api/dna/pivot?track_id={track_id}", None),
        ("POST", "/api/hunter/hunt", {"artist": "Nirvana", "album": "Nevermind"}),
        ("POST", "/api/hunter/acquire", {"results": []}),
        ("POST", "/api/architect/analyze", {"track_id": track_id}),
        ("GET", f"/api/structure/{track_id}", None),
        ("POST", "/api/radio/chaos", {"count": 5}),
        ("POST", "/api/radio/flow", {"current_track_id": track_id, "count": 5}),
        ("GET", "/api/radio/discovery?n=5", None),
        ("POST", "/api/radio/queue", {"seed_track": track_id, "length": 5}),
        ("POST", "/api/playback/record", {"track_id": track_id, "completion_rate": 0.9}),
        ("POST", "/api/agent/query", {"text": "Give me one observation about my library"}),
        ("GET", f"/api/agent/fact-drop?track_id={track_id}", None),
        ("GET", "/api/journal", None),
        ("POST", "/api/undo", {"n": 1}),
        ("POST", "/api/pipeline/start", {}),
        ("GET", "/api/pipeline/status/invalid", None),
        ("GET", "/api/pipeline/jobs", None),
        ("GET", f"/api/stream/{track_id}", None),
    ]


def main() -> int:
    import lyra_api

    REPORTS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ROOT / "lyra_registry.db"))
    cur = con.cursor()
    row = cur.execute("SELECT track_id FROM tracks LIMIT 1").fetchone()
    con.close()
    track_id = row[0] if row else "1"

    doc_endpoints = _collect_doc_endpoints()
    app_routes = _collect_app_routes(lyra_api.app)
    missing_doc_endpoints = []
    for ep in doc_endpoints:
        base = ep.split("<")[0]
        if not any(route.startswith(base) for route in app_routes):
            missing_doc_endpoints.append(ep)

    import_failures = _import_sweep()
    client = lyra_api.app.test_client()

    endpoint_results: list[EndpointResult] = []
    fail_500: list[EndpointResult] = []

    for method, path, payload in _smoke_cases(track_id):
        resp = None
        body = None
        for attempt in range(3):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if method == "GET":
                    resp = client.get(path)
                else:
                    resp = client.post(path, json=payload)
            body = resp.get_json(silent=True)
            # Transient sqlite contention is expected under write-heavy endpoint bursts.
            if resp.status_code >= 500 and isinstance(body, dict) and "database is locked" in str(body.get("error", "")).lower():
                time.sleep(0.25 * (attempt + 1))
                continue
            break
        assert resp is not None
        result = EndpointResult(method=method, path=path, status=resp.status_code, body=body)
        endpoint_results.append(result)
        if resp.status_code >= 500:
            fail_500.append(result)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "doc_endpoint_count": len(doc_endpoints),
        "app_route_count": len(app_routes),
        "missing_doc_endpoints_in_app": missing_doc_endpoints,
        "import_failure_count": len(import_failures),
        "import_failures": import_failures,
        "endpoint_count": len(endpoint_results),
        "endpoint_fail_500_count": len(fail_500),
        "endpoint_results": [
            {"method": r.method, "path": r.path, "status": r.status, "body": r.body}
            for r in endpoint_results
        ],
        "ok": (not missing_doc_endpoints) and (not import_failures) and (not fail_500),
    }

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out = REPORTS / f"backend_surface_audit_{stamp}.json"
    latest = REPORTS / "backend_surface_audit_latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[INFO] report={out}")
    print(f"[INFO] latest={latest}")
    print(f"[INFO] endpoint_fail_500={len(fail_500)}")
    print(f"[INFO] import_failures={len(import_failures)}")
    print(f"[INFO] missing_doc_endpoints={len(missing_doc_endpoints)}")
    print(f"[INFO] overall={'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
