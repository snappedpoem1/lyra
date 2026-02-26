"""CLI wrapper for score sanity audit."""

from __future__ import annotations

import json

from oracle.score_audit import run_audit, write_report


def main() -> None:
    report = run_audit()
    out = write_report()
    print(json.dumps({"report_path": str(out), "coverage_ok": report["coverage_ok"]}, indent=2))


if __name__ == "__main__":
    main()
