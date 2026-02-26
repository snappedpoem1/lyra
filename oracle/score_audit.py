"""Lightweight sanity audit for 10-dimension track scores."""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import mean
from typing import Dict, List, Set

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


TAG_HINTS = {
    "energy": {
        "high": {"metal", "hardcore", "punk", "drill", "trap", "industrial", "aggressive"},
        "low": {"ambient", "drone", "acoustic", "lullaby", "chillout"},
    },
    "valence": {
        "high": {"happy", "uplifting", "party", "dance", "pop"},
        "low": {"sad", "depressive", "melancholic", "dark", "doom"},
    },
    "tension": {
        "high": {"anxious", "tense", "chaotic", "horror", "industrial"},
        "low": {"calm", "relaxed", "peaceful", "serene"},
    },
    "density": {
        "high": {"wall of sound", "orchestral", "maximal", "dense"},
        "low": {"minimal", "solo", "acoustic", "sparse"},
    },
    "warmth": {
        "high": {"soul", "jazz", "rnb", "analog", "vintage", "warm"},
        "low": {"cold", "glitch", "harsh", "robotic"},
    },
    "movement": {
        "high": {"dance", "techno", "house", "dnb", "club"},
        "low": {"ambient", "drone", "downtempo"},
    },
    "space": {
        "high": {"atmospheric", "ambient", "shoegaze", "reverb", "spacious"},
        "low": {"dry", "intimate", "lofi"},
    },
    "rawness": {
        "high": {"lofi", "garage", "punk", "distorted", "raw"},
        "low": {"polished", "clean", "hi-fi", "glossy"},
    },
    "complexity": {
        "high": {"progressive", "jazz", "math rock", "technical", "fusion"},
        "low": {"simple", "pop", "minimal"},
    },
    "nostalgia": {
        "high": {"retro", "classic", "vintage", "oldschool"},
        "low": {"modern", "contemporary", "futuristic"},
    },
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


def _track_tags(conn, track_id: str) -> Set[str]:
    cur = conn.cursor()
    tags: Set[str] = set()

    cur.execute("SELECT genre, subgenres FROM tracks WHERE track_id = ?", (track_id,))
    row = cur.fetchone()
    if row:
        for value in row:
            if not value:
                continue
            for part in str(value).split(","):
                token = part.strip().lower()
                if token:
                    tags.add(token)

    cur.execute(
        """
        SELECT provider, payload_json
        FROM enrich_cache
        WHERE lookup_key IN (?, ?, ?)
        """,
        (f"lastfm:{track_id}", f"acousticbrainz:{track_id}", f"musicnn:{track_id}"),
    )
    for provider, payload_json in cur.fetchall():
        if not payload_json:
            continue
        try:
            payload = json.loads(payload_json)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        raw_tags = payload.get("tags") or payload.get("top_tags") or []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                token = str(t).strip().lower()
                if token:
                    tags.add(token)
        # Include mood labels from AcousticBrainz as hints.
        moods = payload.get("mood_scores")
        if provider == "acousticbrainz" and isinstance(moods, dict):
            for key, score in moods.items():
                try:
                    if float(score) >= 0.6:
                        tags.add(str(key).replace("mood_", "").strip().lower())
                except (TypeError, ValueError):
                    continue

    return tags


def _tag_expected_direction(tags: Set[str], dim: str) -> str:
    hints = TAG_HINTS.get(dim, {})
    highs = hints.get("high", set())
    lows = hints.get("low", set())
    high_hits = any(h in tags for h in highs)
    low_hits = any(l in tags for l in lows)
    if high_hits and not low_hits:
        return "high"
    if low_hits and not high_hits:
        return "low"
    return "none"


def _tag_alignment(conn, sample_limit: int = 600) -> Dict[str, object]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.track_id, ts.energy, ts.valence, ts.tension, ts.density, ts.warmth,
               ts.movement, ts.space, ts.rawness, ts.complexity, ts.nostalgia
        FROM tracks t
        JOIN track_scores ts ON ts.track_id = t.track_id
        WHERE t.status='active'
        ORDER BY ts.scored_at DESC
        LIMIT ?
        """,
        (int(sample_limit),),
    )
    rows = cur.fetchall()
    if not rows:
        return {"sampled_tracks": 0, "tracks_with_hints": 0, "checks": 0, "agreement_rate": 0.0}

    checks = 0
    hits = 0
    tracks_with_hints = 0
    mismatches: List[Dict[str, object]] = []

    for row in rows:
        tid = row[0]
        if any(row[idx + 1] is None for idx, _ in enumerate(DIMS)):
            continue
        scores = {dim: float(row[idx + 1]) for idx, dim in enumerate(DIMS)}
        tags = _track_tags(conn, tid)
        if not tags:
            continue
        per_track_checks = 0
        for dim in DIMS:
            direction = _tag_expected_direction(tags, dim)
            if direction == "none":
                continue
            per_track_checks += 1
            checks += 1
            value = scores[dim]
            ok = (direction == "high" and value >= 0.55) or (direction == "low" and value <= 0.45)
            if ok:
                hits += 1
            elif len(mismatches) < 15:
                mismatches.append(
                    {
                        "track_id": tid,
                        "dimension": dim,
                        "expected": direction,
                        "score": value,
                        "tags": sorted(list(tags))[:6],
                    }
                )
        if per_track_checks:
            tracks_with_hints += 1

    return {
        "sampled_tracks": len(rows),
        "tracks_with_hints": tracks_with_hints,
        "checks": checks,
        "agreement_rate": round((hits / checks), 4) if checks else 0.0,
        "mismatches": mismatches,
    }


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

    tag_alignment = _tag_alignment(conn)

    conn.close()

    return {
        "timestamp": int(time.time()),
        "active_tracks": active_tracks,
        "scored_tracks": scored_tracks,
        "coverage_ok": active_tracks == scored_tracks,
        "dimension_stats": dim_stats,
        "artist_expectation_checks": artist_checks,
        "tag_alignment": tag_alignment,
    }


def write_report(path: Path | None = None) -> Path:
    report = run_audit()
    if path is None:
        reports_dir = Path("Reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"score_sanity_audit_{int(time.time())}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
