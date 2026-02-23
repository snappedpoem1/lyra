"""Dimensional scoring for tracks.

Priority 2A:
- Use CLAP anchor phrases (see oracle.anchors.ANCHORS)
- Compare track embeddings vs anchors to infer dimension values in [0, 1]
- Persist into `track_scores` table

Notes:
- v1 scoring is CLAP-only; later we can blend Architect features + metadata priors.
- Writes are gated by LYRA_WRITE_MODE.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from oracle.anchors import ANCHORS
from oracle.chroma_store import LyraChromaStore
from oracle.db.schema import get_connection, get_write_mode
from oracle.embedders.clap_embedder import CLAPEmbedder
from oracle.perf import auto_workers
from oracle.runtime_state import wait_if_paused
from oracle.vibe_descriptors import describe_scores

logger = logging.getLogger(__name__)

# Use music-specific CLAP model (fallback handled in embedder)
MODEL_NAME = "laion/larger_clap_music"


@dataclass(frozen=True)
class TrackScores:
    track_id: str
    scores: Dict[str, float]
    scored_at: float
    score_version: int = 1


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(len(a)):
        av = float(a[i])
        bv = float(b[i])
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return float(dot / (math.sqrt(norm_a) * math.sqrt(norm_b)))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@lru_cache(maxsize=1)
def _get_embedder() -> CLAPEmbedder:
    return CLAPEmbedder(model_name=MODEL_NAME)


@lru_cache(maxsize=1)
def _get_store() -> LyraChromaStore:
    return LyraChromaStore(persist_dir="./chroma_storage")


@lru_cache(maxsize=1)
def _anchor_embeddings() -> Dict[str, Dict[str, List[List[float]]]]:
    """Compute and cache anchor embeddings."""
    embedder = _get_embedder()

    out: Dict[str, Dict[str, List[List[float]]]] = {}
    for dim, poles in ANCHORS.items():
        out[dim] = {"low": [], "high": []}
        for pole in ("low", "high"):
            for phrase in poles.get(pole, []):
                vec = embedder.embed_text(phrase)
                if vec is None:
                    continue
                out[dim][pole].append(vec.tolist())

    return out


def _score_dimension(track_vec: List[float], dim: str) -> Optional[float]:
    anchors = _anchor_embeddings().get(dim)
    if not anchors:
        return None

    highs = anchors.get("high") or []
    lows = anchors.get("low") or []
    if not highs or not lows:
        return None

    high_sim = sum(_cosine(track_vec, h) for h in highs) / max(len(highs), 1)
    low_sim = sum(_cosine(track_vec, l) for l in lows) / max(len(lows), 1)

    # delta in [-2, 2] (cosine diff); map to [0, 1]
    delta = high_sim - low_sim
    score = 0.5 + (delta / 2.0)
    return round(_clamp01(float(score)), 4)


def score_track(track_id: str, *, persist: bool = True, force: bool = False) -> Dict[str, Any]:
    """Score one track and optionally persist.

    Returns:
        JSON-friendly dict: {track_id, scores, persisted, write_mode}
    """
    track_id = (track_id or "").strip()
    if not track_id:
        raise ValueError("track_id is required")

    if persist and get_write_mode() != "apply_allowed":
        persist = False

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    if not force:
        cursor.execute("SELECT track_id FROM track_scores WHERE track_id = ?", (track_id,))
        if cursor.fetchone():
            conn.close()
            return {
                "track_id": track_id,
                "scores": None,
                "persisted": False,
                "skipped": True,
                "reason": "already_scored",
                "write_mode": get_write_mode(),
            }

    store = _get_store()
    embeddings = store.get_embeddings([track_id])
    vec = embeddings.get(track_id)
    if not vec:
        conn.close()
        return {
            "track_id": track_id,
            "scores": None,
            "persisted": False,
            "skipped": True,
            "reason": "missing_embedding",
            "write_mode": get_write_mode(),
        }

    scores: Dict[str, float] = {}
    for dim in ANCHORS.keys():
        val = _score_dimension(vec, dim)
        if val is None:
            continue
        scores[dim] = val

    scored_at = time.time()
    persisted = False

    if persist:
        cursor.execute(
            """
            INSERT OR REPLACE INTO track_scores (
                track_id,
                energy, valence, tension, density,
                warmth, movement, space, rawness,
                complexity, nostalgia,
                scored_at,
                score_version
            ) VALUES (
                ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?,
                ?
            )
            """,
            (
                track_id,
                scores.get("energy"),
                scores.get("valence"),
                scores.get("tension"),
                scores.get("density"),
                scores.get("warmth"),
                scores.get("movement"),
                scores.get("space"),
                scores.get("rawness"),
                scores.get("complexity"),
                scores.get("nostalgia"),
                scored_at,
                1,
            ),
        )
        conn.commit()
        persisted = True

    conn.close()

    return {
        "track_id": track_id,
        "scores": scores,
        "vibe": describe_scores(scores),
        "persisted": persisted,
        "skipped": False,
        "write_mode": get_write_mode(),
    }


def score_all(
    *,
    limit: int = 0,
    persist: bool = True,
    force: bool = False,
    workers: int = 0,
) -> Dict[str, Any]:
    """Score the whole library (or a limited subset).

    Args:
        limit: 0 = all
        persist: write results to DB if allowed
        force: rescore even if already present

    Returns:
        Stats dict.
    """
    if persist and get_write_mode() != "apply_allowed":
        persist = False

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    # Some legacy databases may not have `created_at`; SQLite always provides `rowid`.
    sql = "SELECT track_id FROM tracks WHERE status = 'active' ORDER BY rowid DESC"
    params: Tuple[Any, ...] = ()
    if limit and int(limit) > 0:
        sql += " LIMIT ?"
        params = (int(limit),)

    cursor.execute(sql, params)
    ids = [row[0] for row in cursor.fetchall() if row and row[0]]
    conn.close()

    stats = {"total": len(ids), "scored": 0, "skipped": 0, "persisted": 0, "errors": 0}
    if workers <= 0:
        workers = auto_workers("cpu")
    workers = max(1, min(int(workers), 24))
    stats["workers"] = workers

    def _score_one(track_id: str) -> Tuple[str, Dict[str, Any]]:
        wait_if_paused("score")
        return track_id, score_track(track_id, persist=persist, force=force)

    if workers == 1:
        for tid in ids:
            try:
                _, result = _score_one(tid)
                if result.get("skipped"):
                    stats["skipped"] += 1
                    reason = result.get("reason", "unknown")
                    if reason == "missing_embedding":
                        stats["missing_embedding"] = stats.get("missing_embedding", 0) + 1
                else:
                    stats["scored"] += 1
                    if result.get("persisted"):
                        stats["persisted"] += 1
            except Exception as e:
                logger.warning("Scoring failed for %s: %s", tid, str(e))
                stats["errors"] += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_score_one, tid) for tid in ids]
            for fut in as_completed(futures):
                try:
                    _tid, result = fut.result()
                    if result.get("skipped"):
                        stats["skipped"] += 1
                        reason = result.get("reason", "unknown")
                        if reason == "missing_embedding":
                            stats["missing_embedding"] = stats.get("missing_embedding", 0) + 1
                    else:
                        stats["scored"] += 1
                        if result.get("persisted"):
                            stats["persisted"] += 1
                except Exception as e:
                    logger.warning("Scoring failed: %s", str(e))
                    stats["errors"] += 1

    stats["write_mode"] = get_write_mode()
    return stats
