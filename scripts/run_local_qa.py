#!/usr/bin/env python3
"""Run local Lyra Oracle QA checks (DB + API smoke)."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
ORACLE_DB = ROOT / "oracle.db"
ORACLE_LIBRARY_DB = ROOT / "oracle_library.db"
LYRA_REGISTRY_DB = ROOT / "lyra_registry.db"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def fmt_ts(ts: float | None) -> str:
    if not ts:
        return "None"
    return datetime.fromtimestamp(ts, UTC).isoformat()


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        print(f"[PASS] {name}" + (f" | {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        msg = f"{name} | {detail}"
        self.failures.append(msg)
        print(f"[FAIL] {msg}")

    def warn(self, name: str, detail: str) -> None:
        msg = f"{name} | {detail}"
        self.warnings.append(msg)
        print(f"[WARN] {msg}")


def get_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        rows = cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows]


def has_unique_index_on_column(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    for index_row in cur.execute(f"PRAGMA index_list('{table}')").fetchall():
        index_name = index_row[1]
        is_unique = bool(index_row[2])
        if not is_unique:
            continue
        index_cols = cur.execute(f"PRAGMA index_info('{index_name}')").fetchall()
        if any(col[2] == column for col in index_cols):
            return True
    return False


def require_columns(actual: Iterable[str], required: Iterable[str]) -> set[str]:
    return set(required) - set(actual)


def run_db_checks(report: Report, sample_size: int, max_missing_pct: float, freshness_days: int) -> None:
    print("\n== DB Checks ==")

    for db_path in [ORACLE_DB, ORACLE_LIBRARY_DB, LYRA_REGISTRY_DB]:
        if db_path.exists():
            tables = get_tables(db_path)
            report.ok(f"tables:{db_path.name}", f"{len(tables)} table(s)")
        else:
            report.fail(f"db_exists:{db_path.name}", "missing file")

    if not ORACLE_LIBRARY_DB.exists():
        report.fail("oracle_library", "oracle_library.db missing, cannot continue library checks")
        return

    with sqlite3.connect(ORACLE_LIBRARY_DB) as con:
        cur = con.cursor()

        table_row = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'"
        ).fetchone()
        if not table_row or not table_row[0]:
            report.fail("tracks_table", "tracks table missing in oracle_library.db")
            return
        tracks_sql = table_row[0]
        report.ok("tracks_table", "exists in oracle_library.db")

        cols_info = cur.execute("PRAGMA table_info('tracks')").fetchall()
        col_names = [c[1] for c in cols_info]
        missing = require_columns(
            col_names,
            ["filepath", "artist", "album", "title", "duration", "content_hash", "updated_at"],
        )
        if missing:
            report.fail("tracks_columns", f"missing columns: {sorted(missing)}")
        else:
            report.ok("tracks_columns", "required columns present")

        filepath_notnull = any(c[1] == "filepath" and int(c[3]) == 1 for c in cols_info)
        if filepath_notnull:
            report.ok("tracks_filepath_not_null")
        else:
            report.fail("tracks_filepath_not_null", "filepath column is nullable")

        filepath_unique = ("filepath TEXT UNIQUE" in tracks_sql.upper()) or has_unique_index_on_column(
            cur, "tracks", "filepath"
        )
        if filepath_unique:
            report.ok("tracks_filepath_unique")
        else:
            report.fail("tracks_filepath_unique", "no unique constraint/index on filepath")

        total_tracks = cur.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        if total_tracks > 0:
            report.ok("population_total_tracks", str(total_tracks))
        else:
            report.fail("population_total_tracks", "0 rows")

        ts_col = None
        for candidate in ["scanned_at", "updated_at", "added_at", "created_at"]:
            if candidate in col_names:
                ts_col = candidate
                break

        if ts_col:
            min_ts, max_ts = cur.execute(f"SELECT MIN({ts_col}), MAX({ts_col}) FROM tracks").fetchone()
            report.ok("population_timestamps", f"{ts_col}: min={fmt_ts(min_ts)} max={fmt_ts(max_ts)}")
            if max_ts:
                age_days = (datetime.now(UTC).timestamp() - float(max_ts)) / 86400.0
                if age_days > freshness_days:
                    report.warn(
                        "population_freshness",
                        f"latest {ts_col} is {age_days:.1f} day(s) old (threshold {freshness_days})",
                    )
                else:
                    report.ok("population_freshness", f"{age_days:.1f} day(s) old")
        else:
            report.warn("population_timestamps", "no scanned_at/updated_at/added_at/created_at column found")

        integrity_checks = {
            "null_filepath": "SELECT COUNT(*) FROM tracks WHERE filepath IS NULL OR trim(filepath)=''",
            "null_artist": "SELECT COUNT(*) FROM tracks WHERE artist IS NULL OR trim(artist)=''",
            "null_title": "SELECT COUNT(*) FROM tracks WHERE title IS NULL OR trim(title)=''",
            "bad_duration_nonpositive": "SELECT COUNT(*) FROM tracks WHERE duration IS NULL OR duration<=0",
            "missing_hash": "SELECT COUNT(*) FROM tracks WHERE content_hash IS NULL OR trim(content_hash)=''",
            "dupe_filepath": (
                "SELECT COUNT(*) FROM ("
                "SELECT filepath,COUNT(*) c FROM tracks GROUP BY filepath HAVING c>1)"
            ),
        }
        for name, sql in integrity_checks.items():
            value = cur.execute(sql).fetchone()[0]
            if value == 0:
                report.ok(f"integrity:{name}")
            else:
                report.fail(f"integrity:{name}", f"{value} offending row(s)")

        paths = [row[0] for row in cur.execute(
            "SELECT filepath FROM tracks ORDER BY RANDOM() LIMIT ?",
            (sample_size,),
        ).fetchall()]
        missing_on_disk = sum(1 for p in paths if p and not os.path.exists(p))
        missing_pct = (missing_on_disk / max(len(paths), 1)) * 100.0
        if missing_pct <= max_missing_pct:
            report.ok(
                "accuracy:filepath_exists",
                f"missing {missing_on_disk}/{len(paths)} ({missing_pct:.2f}%)",
            )
        else:
            report.fail(
                "accuracy:filepath_exists",
                f"missing {missing_on_disk}/{len(paths)} ({missing_pct:.2f}%) > {max_missing_pct:.2f}%",
            )

        too_short = cur.execute("SELECT COUNT(*) FROM tracks WHERE duration < 30").fetchone()[0]
        too_long = cur.execute("SELECT COUNT(*) FROM tracks WHERE duration > 1200").fetchone()[0]
        suspicious_artist_chars = cur.execute(
            "SELECT COUNT(*) FROM tracks WHERE artist GLOB '*[0-9][0-9][0-9][0-9]*'"
        ).fetchone()[0]
        report.ok(
            "accuracy:metadata_plausibility",
            f"short<{30}s={too_short}, long>{1200}s={too_long}, artist_4digits={suspicious_artist_chars}",
        )

        duplicate_groups = cur.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT content_hash,COUNT(*) c FROM tracks GROUP BY content_hash HAVING c>1)"
        ).fetchone()[0]
        report.ok("accuracy:duplicate_hash_groups", str(duplicate_groups))

    if not LYRA_REGISTRY_DB.exists():
        report.fail("lyra_registry", "lyra_registry.db missing, cannot validate primary runtime DB")
        return

    with sqlite3.connect(LYRA_REGISTRY_DB) as con:
        cur = con.cursor()

        table_row = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'"
        ).fetchone()
        if not table_row or not table_row[0]:
            report.fail("lyra:tracks_table", "tracks table missing in lyra_registry.db")
            return
        tracks_sql = table_row[0]
        report.ok("lyra:tracks_table", "exists in lyra_registry.db")

        cols_info = cur.execute("PRAGMA table_info('tracks')").fetchall()
        col_names = [c[1] for c in cols_info]
        missing = require_columns(
            col_names,
            [
                "track_id",
                "filepath",
                "artist",
                "title",
                "duration",
                "content_hash",
                "status",
                "updated_at",
            ],
        )
        if missing:
            report.fail("lyra:tracks_columns", f"missing columns: {sorted(missing)}")
        else:
            report.ok("lyra:tracks_columns", "required columns present")

        filepath_unique = ("FILEPATH TEXT UNIQUE" in tracks_sql.upper()) or has_unique_index_on_column(
            cur, "tracks", "filepath"
        )
        if filepath_unique:
            report.ok("lyra:tracks_filepath_unique")
        else:
            report.fail("lyra:tracks_filepath_unique", "no unique constraint/index on filepath")

        total_tracks = cur.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        if total_tracks > 0:
            report.ok("lyra:population_total_tracks", str(total_tracks))
        else:
            report.fail("lyra:population_total_tracks", "0 rows")

        ts_col = None
        for candidate in ["updated_at", "last_seen_at", "added_at", "created_at"]:
            if candidate in col_names:
                ts_col = candidate
                break

        if ts_col:
            min_ts, max_ts = cur.execute(f"SELECT MIN({ts_col}), MAX({ts_col}) FROM tracks").fetchone()
            report.ok("lyra:population_timestamps", f"{ts_col}: min={fmt_ts(min_ts)} max={fmt_ts(max_ts)}")
            if max_ts:
                age_days = (datetime.now(UTC).timestamp() - float(max_ts)) / 86400.0
                if age_days > freshness_days:
                    report.warn(
                        "lyra:population_freshness",
                        f"latest {ts_col} is {age_days:.1f} day(s) old (threshold {freshness_days})",
                    )
                else:
                    report.ok("lyra:population_freshness", f"{age_days:.1f} day(s) old")
        else:
            report.warn("lyra:population_timestamps", "no updated_at/last_seen_at/added_at/created_at column found")

        integrity_checks = {
            "null_filepath": "SELECT COUNT(*) FROM tracks WHERE filepath IS NULL OR trim(filepath)=''",
            "null_artist": "SELECT COUNT(*) FROM tracks WHERE artist IS NULL OR trim(artist)=''",
            "null_title": "SELECT COUNT(*) FROM tracks WHERE title IS NULL OR trim(title)=''",
            "bad_duration_nonpositive": "SELECT COUNT(*) FROM tracks WHERE duration IS NULL OR duration<=0",
            "missing_hash": "SELECT COUNT(*) FROM tracks WHERE content_hash IS NULL OR trim(content_hash)=''",
            "dupe_filepath": (
                "SELECT COUNT(*) FROM ("
                "SELECT filepath,COUNT(*) c FROM tracks GROUP BY filepath HAVING c>1)"
            ),
        }
        for name, sql in integrity_checks.items():
            value = cur.execute(sql).fetchone()[0]
            if value == 0:
                report.ok(f"lyra:integrity:{name}")
            else:
                report.fail(f"lyra:integrity:{name}", f"{value} offending row(s)")

        paths = [row[0] for row in cur.execute(
            "SELECT filepath FROM tracks ORDER BY RANDOM() LIMIT ?",
            (sample_size,),
        ).fetchall()]
        missing_on_disk = sum(1 for p in paths if p and not os.path.exists(p))
        missing_pct = (missing_on_disk / max(len(paths), 1)) * 100.0
        if missing_pct <= max_missing_pct:
            report.ok(
                "lyra:accuracy:filepath_exists",
                f"missing {missing_on_disk}/{len(paths)} ({missing_pct:.2f}%)",
            )
        else:
            report.fail(
                "lyra:accuracy:filepath_exists",
                f"missing {missing_on_disk}/{len(paths)} ({missing_pct:.2f}%) > {max_missing_pct:.2f}%",
            )

        duplicate_groups = cur.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT content_hash,COUNT(*) c FROM tracks GROUP BY content_hash HAVING c>1)"
        ).fetchone()[0]
        report.ok("lyra:accuracy:duplicate_hash_groups", str(duplicate_groups))

        # Scorer integrity checks
        score_cols = {
            "energy",
            "valence",
            "tension",
            "density",
            "warmth",
            "movement",
            "space",
            "rawness",
            "complexity",
            "nostalgia",
            "scored_at",
            "score_version",
        }
        score_table = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='track_scores'"
        ).fetchone()
        if not score_table:
            report.fail("lyra:scorer:table", "track_scores table missing")
        else:
            report.ok("lyra:scorer:table", "track_scores exists")
            cols = {row[1] for row in cur.execute("PRAGMA table_info('track_scores')").fetchall()}
            missing_score_cols = score_cols - cols
            if missing_score_cols:
                report.fail("lyra:scorer:columns", f"missing: {sorted(missing_score_cols)}")
            else:
                report.ok("lyra:scorer:columns", "all scorer columns present")

            scored_total = cur.execute("SELECT COUNT(*) FROM track_scores").fetchone()[0]
            report.ok("lyra:scorer:row_count", str(scored_total))

            null_any = cur.execute(
                """
                SELECT COUNT(*) FROM track_scores
                WHERE energy IS NULL OR valence IS NULL OR tension IS NULL OR density IS NULL
                   OR warmth IS NULL OR movement IS NULL OR space IS NULL OR rawness IS NULL
                   OR complexity IS NULL OR nostalgia IS NULL
                """
            ).fetchone()[0]
            if null_any == 0:
                report.ok("lyra:scorer:null_dimensions")
            else:
                report.fail("lyra:scorer:null_dimensions", f"{null_any} row(s) with missing dimensions")

            bad_range = cur.execute(
                """
                SELECT COUNT(*) FROM track_scores
                WHERE energy < 0 OR energy > 1
                   OR valence < 0 OR valence > 1
                   OR tension < 0 OR tension > 1
                   OR density < 0 OR density > 1
                   OR warmth < 0 OR warmth > 1
                   OR movement < 0 OR movement > 1
                   OR space < 0 OR space > 1
                   OR rawness < 0 OR rawness > 1
                   OR complexity < 0 OR complexity > 1
                   OR nostalgia < 0 OR nostalgia > 1
                """
            ).fetchone()[0]
            if bad_range == 0:
                report.ok("lyra:scorer:range")
            else:
                report.fail("lyra:scorer:range", f"{bad_range} row(s) out of [0,1] range")

            orphan_scores = cur.execute(
                """
                SELECT COUNT(*) FROM track_scores s
                LEFT JOIN tracks t ON t.track_id = s.track_id
                WHERE t.track_id IS NULL
                """
            ).fetchone()[0]
            if orphan_scores == 0:
                report.ok("lyra:scorer:orphans")
            else:
                report.fail("lyra:scorer:orphans", f"{orphan_scores} score row(s) without track")

            missing_active_scores = cur.execute(
                """
                SELECT COUNT(*) FROM tracks t
                LEFT JOIN track_scores s ON s.track_id = t.track_id
                WHERE t.status = 'active' AND s.track_id IS NULL
                """
            ).fetchone()[0]
            if missing_active_scores == 0:
                report.ok("lyra:scorer:active_coverage")
            else:
                report.fail("lyra:scorer:active_coverage", f"{missing_active_scores} active track(s) missing score")


def run_api_checks(report: Report, search_query: str, search_limit: int) -> None:
    print("\n== API Checks ==")
    try:
        import lyra_api
    except Exception as exc:
        report.fail("api_import", f"unable to import lyra_api: {exc}")
        return

    client = lyra_api.app.test_client()

    def check_get(path: str) -> tuple[int, dict | None]:
        resp = client.get(path)
        data = resp.get_json(silent=True)
        return resp.status_code, data if isinstance(data, dict) else None

    code, body = check_get("/health")
    if code == 200 and body and body.get("status") == "ok":
        report.ok("api:/health", "200")
    else:
        report.fail("api:/health", f"status={code}, body={body}")

    code, body = check_get("/api/status")
    if code == 200 and body and isinstance(body.get("tracks"), int):
        report.ok("api:/api/status", f"tracks={body['tracks']}")
    else:
        report.fail("api:/api/status", f"status={code}, body={body}")

    code, body = check_get("/api/library/tracks?limit=10")
    if code == 200 and body and "tracks" in body:
        count = int(body.get("count", -1))
        if count <= 10:
            report.ok("api:/api/library/tracks", f"count={count}")
        else:
            report.fail("api:/api/library/tracks", f"count={count} exceeds limit=10")
    else:
        report.fail("api:/api/library/tracks", f"status={code}, body={body}")

    req = {"query": search_query, "n": search_limit}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        resp = client.post("/api/search", json=req)
    body = resp.get_json(silent=True)
    if resp.status_code == 200 and isinstance(body, dict) and isinstance(body.get("count"), int):
        count = int(body["count"])
        if count <= search_limit:
            report.ok("api:/api/search", f"count={count} (n={search_limit})")
        else:
            report.fail("api:/api/search", f"count={count} > n={search_limit}")
    else:
        report.fail("api:/api/search", f"status={resp.status_code}, body={body}")

    # SQL/API parity for /api/status (uses lyra_registry.db)
    if LYRA_REGISTRY_DB.exists():
        with sqlite3.connect(LYRA_REGISTRY_DB) as con:
            cur = con.cursor()
            sql_tracks = cur.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        code, body = check_get("/api/status")
        api_tracks = body.get("tracks") if body else None
        if code == 200 and api_tracks == sql_tracks:
            report.ok("parity:/api/status_vs_sql", f"{api_tracks}")
        else:
            report.fail(
                "parity:/api/status_vs_sql",
                f"api={api_tracks}, sql={sql_tracks}, status={code}",
            )
    else:
        report.warn("parity:/api/status_vs_sql", "lyra_registry.db not found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lyra Oracle local QA checks.")
    parser.add_argument("--sample-size", type=int, default=100, help="Filepath existence sample size.")
    parser.add_argument(
        "--max-missing-pct",
        type=float,
        default=2.0,
        help="Fail if sampled missing file percentage exceeds this.",
    )
    parser.add_argument(
        "--freshness-days",
        type=int,
        default=14,
        help="Warn if newest scan/update timestamp is older than this many days.",
    )
    parser.add_argument("--search-query", default="Tyler", help="Query for /api/search smoke check.")
    parser.add_argument("--search-limit", type=int, default=10, help="n for /api/search.")
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip API checks and run DB-only checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = Report()

    print("== Baseline ==")
    report.ok("python_version", sys.version.split()[0])
    report.ok("sqlite_version", sqlite3.sqlite_version)
    if sys.version_info[:2] != (3, 12):
        report.warn("python_version_expected", "project target is Python 3.12")

    run_db_checks(
        report=report,
        sample_size=max(1, args.sample_size),
        max_missing_pct=max(0.0, args.max_missing_pct),
        freshness_days=max(0, args.freshness_days),
    )

    if not args.skip_api:
        run_api_checks(report, search_query=args.search_query, search_limit=max(1, args.search_limit))

    print("\n== Summary ==")
    print(f"Failures: {len(report.failures)}")
    print(f"Warnings: {len(report.warnings)}")
    if report.failures:
        for item in report.failures:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
