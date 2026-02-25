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
<<<<<<< HEAD
=======
import threading
>>>>>>> fc77b41 (Update workspace state and diagnostics)
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
<<<<<<< HEAD
from typing import Any, Dict, Iterable, List, Optional, Tuple
=======
from typing import Any, Dict, List, Optional, Tuple
>>>>>>> fc77b41 (Update workspace state and diagnostics)

from oracle.anchors import ANCHORS
from oracle.chroma_store import LyraChromaStore
from oracle.db.schema import get_connection, get_write_mode
from oracle.embedders.clap_embedder import CLAPEmbedder
<<<<<<< HEAD
from oracle.perf import auto_workers
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
from oracle.runtime_state import wait_if_paused
from oracle.vibe_descriptors import describe_scores

logger = logging.getLogger(__name__)
<<<<<<< HEAD

# Use music-specific CLAP model (fallback handled in embedder)
MODEL_NAME = "laion/larger_clap_music"
=======
_THREAD_LOCAL = threading.local()

# Use music-specific CLAP model (fallback handled in embedder)
MODEL_NAME = "laion/larger_clap_music"
SCORE_VERSION = 2
CALIBRATION_SAMPLE_SIZE = 2000
CALIBRATION_Q_LOW = 0.05
CALIBRATION_Q_HIGH = 0.95
>>>>>>> fc77b41 (Update workspace state and diagnostics)


@dataclass(frozen=True)
class TrackScores:
    track_id: str
    scores: Dict[str, float]
    scored_at: float
<<<<<<< HEAD
    score_version: int = 1
=======
    score_version: int = SCORE_VERSION
>>>>>>> fc77b41 (Update workspace state and diagnostics)


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


<<<<<<< HEAD
=======
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


>>>>>>> fc77b41 (Update workspace state and diagnostics)
@lru_cache(maxsize=1)
def _get_embedder() -> CLAPEmbedder:
    return CLAPEmbedder(model_name=MODEL_NAME)


<<<<<<< HEAD
@lru_cache(maxsize=1)
def _get_store() -> LyraChromaStore:
    return LyraChromaStore(persist_dir="./chroma_storage")
=======
def _get_store() -> LyraChromaStore:
    # Chroma client objects are not reliably thread-safe for concurrent reads.
    # Keep one store per worker thread to avoid cross-thread tenant/client errors.
    store = getattr(_THREAD_LOCAL, "chroma_store", None)
    if store is None:
        store = LyraChromaStore(persist_dir="./chroma_storage")
        _THREAD_LOCAL.chroma_store = store
    return store
>>>>>>> fc77b41 (Update workspace state and diagnostics)


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


<<<<<<< HEAD
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
=======
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
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
<<<<<<< HEAD
                1,
=======
                SCORE_VERSION,
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
<<<<<<< HEAD
    if workers <= 0:
        workers = auto_workers("cpu")
    workers = max(1, min(int(workers), 24))
=======
    # Chroma local client access is not reliable under concurrent per-track fetches.
    # Keep scoring single-threaded until embedding fetch is refactored to batch mode.
    if workers <= 0:
        workers = 1
    workers = max(1, min(int(workers), 24))
    if workers != 1:
        logger.warning(
            "Parallel scoring is currently disabled due Chroma concurrency limits; forcing workers=1."
        )
        workers = 1
>>>>>>> fc77b41 (Update workspace state and diagnostics)
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
