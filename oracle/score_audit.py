"""Lightweight sanity audit for 10-dimension track scores."""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import mean
from typing import Dict, List

from oracle.db.schema import get_connection


DIMS = [
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
]


EXPECTATIONS = {
    "Boards of Canada": {"energy_max": 0.45, "space_min": 0.50, "nostalgia_min": 0.45},
    "Death Grips": {"energy_min": 0.55, "tension_min": 0.45, "rawness_min": 0.55},
    "Massive Attack": {"energy_max": 0.60, "space_min": 0.50, "density_min": 0.45},
    "Frank Ocean": {"energy_max": 0.65, "warmth_min": 0.45},
}


def _fetch_artist_scores(conn, artist: str) -> List[Dict[str, float]]:
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {", ".join(f"ts.{d}" for d in DIMS)}
        FROM tracks t
        JOIN track_scores ts ON ts.track_id = t.track_id
        WHERE t.status='active' AND lower(t.artist)=lower(?)
        """,
        (artist,),
    )
    rows = cur.fetchall()
    out: List[Dict[str, float]] = []
    for row in rows:
        out.append({dim: float(row[idx]) for idx, dim in enumerate(DIMS)})
    return out


def run_audit() -> Dict[str, object]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM tracks WHERE status='active'")
    active_tracks = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM track_scores")
    scored_tracks = int(cur.fetchone()[0])

    dim_stats: Dict[str, Dict[str, float]] = {}
    for dim in DIMS:
        cur.execute(f"SELECT MIN({dim}), MAX({dim}), AVG({dim}) FROM track_scores")
        mn, mx, av = cur.fetchone()
        dim_stats[dim] = {
            "min": float(mn or 0.0),
            "max": float(mx or 0.0),
            "avg": float(av or 0.0),
        }

    artist_checks: Dict[str, Dict[str, object]] = {}
    for artist, rules in EXPECTATIONS.items():
        rows = _fetch_artist_scores(conn, artist)
        if not rows:
            artist_checks[artist] = {"present": False, "tracks": 0, "checks": []}
            continue

        means = {dim: mean([r[dim] for r in rows]) for dim in DIMS}
        checks = []
        for key, threshold in rules.items():
            dim, direction = key.rsplit("_", 1)
            value = means[dim]
            if direction == "min":
                ok = value >= float(threshold)
                checks.append({"rule": key, "value": value, "target": threshold, "ok": ok})
            else:
                ok = value <= float(threshold)
                checks.append({"rule": key, "value": value, "target": threshold, "ok": ok})
        artist_checks[artist] = {
            "present": True,
            "tracks": len(rows),
            "means": means,
            "checks": checks,
        }

    conn.close()

    return {
        "timestamp": int(time.time()),
        "active_tracks": active_tracks,
        "scored_tracks": scored_tracks,
        "coverage_ok": active_tracks == scored_tracks,
        "dimension_stats": dim_stats,
        "artist_expectation_checks": artist_checks,
    }


def write_report(path: Path | None = None) -> Path:
    report = run_audit()
    if path is None:
        reports_dir = Path("Reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"score_sanity_audit_{int(time.time())}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
