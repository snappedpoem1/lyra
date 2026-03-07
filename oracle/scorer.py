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
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor  # kept for potential future parallel use
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from oracle.anchors import ANCHORS
from oracle.chroma_store import LyraChromaStore
from oracle.config import CHROMA_PATH
from oracle.db.schema import get_connection, get_write_mode
from oracle.embedders.clap_embedder import CLAPEmbedder
from oracle.runtime_state import wait_if_paused
from oracle.vibe_descriptors import describe_scores

logger = logging.getLogger(__name__)
_THREAD_LOCAL = threading.local()

# Use music-specific CLAP model (fallback handled in embedder)
MODEL_NAME = "laion/larger_clap_music"
SCORE_VERSION = 2
CALIBRATION_SAMPLE_SIZE = 2000
CALIBRATION_Q_LOW = 0.05
CALIBRATION_Q_HIGH = 0.95


@dataclass(frozen=True)
class TrackScores:
    track_id: str
    scores: Dict[str, float]
    scored_at: float
    score_version: int = SCORE_VERSION


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


def _unit(vec: List[float]) -> List[float]:
    if not vec:
        return []
    norm = math.sqrt(sum(float(x) * float(x) for x in vec))
    if norm <= 0.0:
        return []
    return [float(x) / norm for x in vec]


def _mean_vector(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    n = 0
    for v in vectors:
        if not v or len(v) != dim:
            continue
        for i in range(dim):
            acc[i] += float(v[i])
        n += 1
    if n == 0:
        return []
    return [x / n for x in acc]


def _vector_sub(a: List[float], b: List[float]) -> List[float]:
    if not a or not b or len(a) != len(b):
        return []
    return [float(av) - float(bv) for av, bv in zip(a, b)]


def _is_nonempty_vector(value: Any) -> bool:
    if value is None:
        return False
    try:
        return len(value) > 0
    except Exception:
        return False


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    q = max(0.0, min(1.0, float(q)))
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@lru_cache(maxsize=1)
def _get_embedder() -> CLAPEmbedder:
    return CLAPEmbedder(
        model_name=MODEL_NAME,
        cache_dir=os.getenv("HF_HOME"),
        use_fallback=False,
    )


def _get_store() -> LyraChromaStore:
    # Chroma client objects are not reliably thread-safe for concurrent reads.
    # Keep one store per worker thread to avoid cross-thread tenant/client errors.
    store = getattr(_THREAD_LOCAL, "chroma_store", None)
    if store is None:
        store = LyraChromaStore(persist_dir=CHROMA_PATH)
        _THREAD_LOCAL.chroma_store = store
    return store


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


@lru_cache(maxsize=1)
def _anchor_directions() -> Dict[str, List[float]]:
    """Build normalized direction vectors (high - low) per dimension."""
    directions: Dict[str, List[float]] = {}
    for dim, poles in _anchor_embeddings().items():
        highs = poles.get("high") or []
        lows = poles.get("low") or []
        if not highs or not lows:
            continue
        high_centroid = _unit(_mean_vector(highs))
        low_centroid = _unit(_mean_vector(lows))
        direction = _unit(_vector_sub(high_centroid, low_centroid))
        if direction:
            directions[dim] = direction
    return directions


def _raw_dimension_delta(track_vec: List[float], dim: str) -> Optional[float]:
    direction = _anchor_directions().get(dim)
    if not direction:
        return None
    tvec = _unit(track_vec)
    if not tvec:
        return None
    # Projection onto pole direction: negative=low pole, positive=high pole.
    return float(sum(float(tv) * float(dv) for tv, dv in zip(tvec, direction)))


def _sample_track_vectors(limit: int = CALIBRATION_SAMPLE_SIZE) -> List[List[float]]:
    store = _get_store()
    vectors: List[List[float]] = []

    try:
        result = store.collection.get(include=["embeddings"], limit=int(limit))
        embeddings = result.get("embeddings") if isinstance(result, dict) else None
        if embeddings:
            for emb in embeddings:
                if _is_nonempty_vector(emb):
                    vectors.append(list(emb))
    except Exception as exc:
        logger.debug("Calibration direct fetch failed: %s", exc)

    if vectors:
        return vectors[:limit]

    # Fallback: sample IDs from DB and fetch embeddings by ID.
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT track_id FROM tracks WHERE status = 'active' ORDER BY rowid DESC LIMIT ?", (int(limit),))
        ids = [row[0] for row in cursor.fetchall() if row and row[0]]
        conn.close()
        emb_map = store.get_embeddings(ids)
        for tid in ids:
            vec = emb_map.get(tid)
            if _is_nonempty_vector(vec):
                vectors.append(vec)
    except Exception as exc:
        logger.debug("Calibration DB fallback failed: %s", exc)

    return vectors[:limit]


@lru_cache(maxsize=1)
def _dimension_calibration() -> Dict[str, Dict[str, float]]:
    """Compute per-dimension normalization bands from library embeddings."""
    vectors = _sample_track_vectors(limit=CALIBRATION_SAMPLE_SIZE)
    calibration: Dict[str, Dict[str, float]] = {}
    if not vectors:
        return calibration

    for dim in ANCHORS.keys():
        deltas: List[float] = []
        for vec in vectors:
            raw = _raw_dimension_delta(vec, dim)
            if raw is None:
                continue
            deltas.append(raw)
        if not deltas:
            continue
        lo = _quantile(deltas, CALIBRATION_Q_LOW)
        hi = _quantile(deltas, CALIBRATION_Q_HIGH)
        calibration[dim] = {"lo": lo, "hi": hi}

    return calibration


def _score_dimension(track_vec: List[float], dim: str) -> Optional[float]:
    raw = _raw_dimension_delta(track_vec, dim)
    if raw is None:
        return None

    cal = _dimension_calibration().get(dim)
    if cal:
        lo = float(cal.get("lo", 0.0))
        hi = float(cal.get("hi", 0.0))
        if hi > lo + 1e-9:
            # Smoothly map around observed library band to avoid hard saturation.
            mid = (lo + hi) / 2.0
            half_band = max((hi - lo) / 2.0, 1e-9)
            z = (raw - mid) / half_band
            score = _sigmoid(z)
            return round(_clamp01(score), 4)

    # Fallback for tiny/degenerate bands.
    score = 0.5 + (raw * 3.0)
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
                SCORE_VERSION,
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
    workers: int = 0,  # kept for API compat; always 1 — batch fetch removes concurrency need
) -> Dict[str, Any]:
    """Score the whole library (or a limited subset).

    Batch-optimised path:
      1.  Fetch all active track IDs from SQLite in one query.
      2.  Pre-fetch already-scored IDs in one IN-clause query (skip step if force=True).
      3.  Batch-fetch all needed embeddings from ChromaDB in a single ``get()`` call.
      4.  Run pure-math scoring per track (no I/O inside the loop).
      5.  Persist all results in one ``executemany`` transaction.

    Args:
        limit: Maximum tracks to process (0 = all).
        persist: Write results to DB when write-mode allows.
        force: Rescore even tracks that already have scores.
        workers: Ignored — kept for backwards-compatible call sites.

    Returns:
        Stats dict with total/scored/skipped/persisted/errors counts.
    """
    if persist and get_write_mode() != "apply_allowed":
        persist = False

    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        sql = "SELECT track_id FROM tracks WHERE status = 'active' ORDER BY rowid DESC"
        params: Tuple[Any, ...] = ()
        if limit and int(limit) > 0:
            sql += " LIMIT ?"
            params = (int(limit),)
        cursor.execute(sql, params)
        ids = [row[0] for row in cursor.fetchall() if row and row[0]]

        # Pre-fetch already-scored set in one query — avoids N per-track SELECT calls.
        if not force and ids:
            ph = ",".join("?" * len(ids))
            cursor.execute(f"SELECT track_id FROM track_scores WHERE track_id IN ({ph})", ids)
            already_scored: set = {row[0] for row in cursor.fetchall()}
        else:
            already_scored = set()
    finally:
        conn.close()

    stats: Dict[str, Any] = {
        "total": len(ids),
        "scored": 0,
        "skipped": len(already_scored),
        "persisted": 0,
        "errors": 0,
        "workers": 1,
        "write_mode": get_write_mode(),
    }

    ids_to_score = [tid for tid in ids if tid not in already_scored]
    if not ids_to_score:
        return stats

    # Single ChromaDB batch call — eliminates N individual get() round-trips.
    store = _get_store()
    try:
        emb_map = store.get_embeddings(ids_to_score)
    except Exception as exc:
        logger.error("Batch embedding fetch failed: %s", exc)
        emb_map = {}

    scored_at = time.time()
    rows_to_insert: List[Tuple] = []

    for tid in ids_to_score:
        wait_if_paused("score")
        vec = emb_map.get(tid)
        if not vec:
            stats["skipped"] += 1
            stats["missing_embedding"] = stats.get("missing_embedding", 0) + 1
            continue
        try:
            scores: Dict[str, float] = {}
            for dim in ANCHORS.keys():
                val = _score_dimension(vec, dim)
                if val is not None:
                    scores[dim] = val
            stats["scored"] += 1
            if persist:
                rows_to_insert.append((
                    tid,
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
                    SCORE_VERSION,
                ))
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", tid, str(exc))
            stats["errors"] += 1

    # Persist all rows in a single transaction.
    if persist and rows_to_insert:
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO track_scores (
                    track_id,
                    energy, valence, tension, density,
                    warmth, movement, space, rawness,
                    complexity, nostalgia,
                    scored_at, score_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
            conn.commit()
            stats["persisted"] = len(rows_to_insert)
        except Exception as exc:
            logger.error("Batch score persist failed: %s", exc)
            conn.rollback()
        finally:
            conn.close()

    return stats
