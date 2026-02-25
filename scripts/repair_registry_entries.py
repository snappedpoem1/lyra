#!/usr/bin/env python3
"""Repair inaccurate rows in lyra_registry.db tracks table."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys
import sqlite3
import subprocess

from mutagen import File as MutagenFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle.db.schema import get_connection, get_write_mode


def read_duration_seconds(path: Path) -> float | None:
    """Return duration in seconds if available."""
    try:
        audio = MutagenFile(str(path), easy=False)
        if audio and audio.info and getattr(audio.info, "length", None):
            duration = float(audio.info.length)
            if duration > 0:
                return duration
    except Exception:
        pass

    try:
        audio = MutagenFile(str(path), easy=True)
        if audio and audio.info and getattr(audio.info, "length", None):
            duration = float(audio.info.length)
            if duration > 0:
                return duration
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            duration = float(proc.stdout.strip())
            if duration > 0:
                return duration
    except Exception:
        pass

    return None


def repair_bad_durations(limit: int = 0) -> int:
    conn = get_connection(timeout=30.0)
    cur = conn.cursor()
    oracle_library_db = ROOT / "oracle_library.db"
    oracle_lib_conn = None
    oracle_lib_cur = None
    if oracle_library_db.exists():
        oracle_lib_conn = sqlite3.connect(oracle_library_db)
        oracle_lib_cur = oracle_lib_conn.cursor()

    sql = (
        "SELECT track_id, filepath FROM tracks "
        "WHERE duration IS NULL OR duration <= 0 "
        "ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC"
    )
    if limit > 0:
        sql += " LIMIT ?"
        rows = cur.execute(sql, (limit,)).fetchall()
    else:
        rows = cur.execute(sql).fetchall()

    fixed = 0
    skipped_missing = 0
    unresolved = 0
    now = time.time()

    for track_id, filepath in rows:
        path = Path(filepath)
        if not path.exists():
            skipped_missing += 1
            continue

        duration = read_duration_seconds(path)
        if not duration and oracle_lib_cur is not None:
            row = oracle_lib_cur.execute(
                "SELECT duration FROM tracks WHERE filepath = ? AND duration > 0 LIMIT 1",
                (filepath,),
            ).fetchone()
            if row:
                duration = float(row[0])
        if not duration:
            unresolved += 1
            continue

        cur.execute(
            "UPDATE tracks SET duration = ?, updated_at = ? WHERE track_id = ?",
            (duration, now, track_id),
        )
        fixed += 1

    conn.commit()

    remaining = cur.execute(
        "SELECT COUNT(*) FROM tracks WHERE duration IS NULL OR duration <= 0"
    ).fetchone()[0]
    if oracle_lib_conn is not None:
        oracle_lib_conn.close()
    conn.close()

    print(f"rows_scanned={len(rows)} fixed={fixed} unresolved={unresolved} missing_files={skipped_missing}")
    print(f"remaining_bad_duration_rows={remaining}")
    return remaining


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair inaccurate entries in lyra_registry.db.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of bad-duration rows to process (0 = all).",
    )
    args = parser.parse_args()

    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: set LYRA_WRITE_MODE=apply_allowed before running repairs.")
        return 1

    remaining = repair_bad_durations(limit=max(0, args.limit))
    return 0 if remaining == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
