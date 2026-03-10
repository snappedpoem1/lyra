"""
One-shot taste backfill bridge.

Reads spotify_history + track_scores from the legacy lyra_registry.db
(flat artist column schema), computes taste dimensions, then writes
taste_profile into the canonical Rust lyra.db.

Usage:
    python scripts/run_taste_backfill.py [--force]
"""
import math
import os
import re
import sys
import sqlite3

LEGACY_DB = os.path.join(os.path.dirname(__file__), "..", "lyra_registry.db")
CANONICAL_DB = os.path.join(
    os.environ.get("APPDATA", ""),
    "com.lyra.player", "db", "lyra.db",
)

DIMS = ["energy", "valence", "tension", "density", "warmth",
        "movement", "space", "rawness", "complexity", "nostalgia"]

MIN_MS_PLAY = 30_000


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)
    s = re.sub(r"\s*feat\.?\s.*", "", s)
    s = re.sub(r"\s*ft\.?\s.*", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    force = "--force" in sys.argv

    leg = sqlite3.connect(LEGACY_DB)
    can = sqlite3.connect(CANONICAL_DB)

    # Check existing canonical confidence
    existing = can.execute("SELECT AVG(confidence) FROM taste_profile").fetchone()[0] or 0.0
    print(f"Canonical taste_profile avg confidence: {existing:.2f}")
    if existing >= 0.5 and not force:
        print("Profile already confident. Use --force to override.")
        return

    # Build scored track index from legacy DB
    # Legacy schema: tracks(track_id TEXT, artist TEXT, title TEXT, ...)
    # track_scores(track_id TEXT, energy, valence, ...)
    rows = leg.execute("""
        SELECT LOWER(TRIM(t.artist)), LOWER(TRIM(t.title)),
               ts.energy, ts.valence, ts.tension, ts.density, ts.warmth,
               ts.movement, ts.space, ts.rawness, ts.complexity, ts.nostalgia
        FROM tracks t
        JOIN track_scores ts ON ts.track_id = t.track_id
        WHERE t.artist IS NOT NULL AND t.title IS NOT NULL
    """).fetchall()

    # Index: (norm_artist, norm_title) -> scores[10]
    score_index: dict[tuple, list[float]] = {}
    for row in rows:
        artist, title = norm(row[0]), norm(row[1])
        score_index[(artist, title)] = list(row[2:])

    print(f"Loaded {len(score_index)} scored tracks from legacy DB")

    # Aggregate spotify_history
    groups = leg.execute("""
        SELECT LOWER(TRIM(artist)), LOWER(TRIM(track)),
               COUNT(*) AS plays,
               SUM(CASE WHEN ms_played < 30000 THEN 1 ELSE 0 END) AS skips,
               COALESCE(SUM(ms_played), 0) AS total_ms
        FROM spotify_history
        WHERE artist IS NOT NULL AND track IS NOT NULL
        GROUP BY LOWER(TRIM(artist)), LOWER(TRIM(track))
        HAVING plays >= 2
        ORDER BY plays DESC
        LIMIT 2000
    """).fetchall()
    print(f"Aggregated {len(groups)} artist+track groups from Spotify history")

    # EMA state
    dims_state = {d: 0.5 for d in DIMS}
    matched = 0

    for artist_lc, title_lc, plays, skips, total_ms in groups:
        # Try normalized lookup
        key = (norm(artist_lc), norm(title_lc))
        scores = score_index.get(key)
        if scores is None:
            # Try direct lowercased lookup
            key2 = (artist_lc.strip(), title_lc.strip())
            scores = score_index.get(key2)
        if scores is None:
            continue

        non_skips = plays - skips
        avg_ms = total_ms / plays if plays > 0 else 0
        positive = non_skips > skips and avg_ms >= MIN_MS_PLAY
        weight = min(math.log2(plays + 1), 3.0)
        alpha = min(0.03 * weight, 0.12)

        for i, dim in enumerate(DIMS):
            old = dims_state[dim]
            target = scores[i] if positive else (1.0 - scores[i])
            dims_state[dim] = max(0.0, min(1.0, old * (1 - alpha) + target * alpha))

        matched += 1

    print(f"Matched {matched} tracks with scores")
    if matched == 0:
        print("No matches — nothing to write.")
        return

    confidence = min(matched / (matched + 20), 0.85)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    can.execute("BEGIN")
    for dim in DIMS:
        can.execute("""
            INSERT INTO taste_profile (dimension, value, confidence, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dimension) DO UPDATE SET
              value=excluded.value, confidence=excluded.confidence,
              last_updated=excluded.last_updated
        """, (dim, dims_state[dim], confidence, now))
    can.execute("COMMIT")

    print(f"\nWrote taste_profile to canonical DB (confidence={confidence:.2f}):\n")
    for dim in DIMS:
        v = dims_state[dim]
        bar = "#" * int(v * 20)
        print(f"  {dim:<12} {bar:<20} {v:.3f}")

    leg.close()
    can.close()


if __name__ == "__main__":
    main()
