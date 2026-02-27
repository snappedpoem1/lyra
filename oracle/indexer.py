"""Embedding indexer for Lyra Oracle.

Auto-scores tracks after indexing when auto_score=True (default).
"""

from __future__ import annotations

from pathlib import Path
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
import time

from dotenv import load_dotenv

from oracle.chroma_store import LyraChromaStore
from oracle.db.schema import get_connection, get_write_mode
from oracle.embedders.clap_embedder import CLAPEmbedder
from oracle.perf import auto_workers
from oracle.runtime_state import wait_if_paused, get_profile

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Use music-specific CLAP model (fallback handled in embedder)
MODEL_NAME = "laion/larger_clap_music"
MODEL_KEY = "clap_htsat_unfused"


def index_library(
    library_path: Optional[str] = None,
    limit: int = 0,
    force_reindex: bool = False,
    auto_score: bool = True,
    workers: int = 0,
    embed_batch: int = 0,
) -> Dict[str, int]:
    """Index library tracks with CLAP embeddings.

    Args:
        library_path: Optional path to scope indexing
        limit: Max tracks to index (0 = all)
        force_reindex: Re-index already indexed tracks
        auto_score: Score newly indexed tracks automatically

    Returns:
        Stats dict with indexed/failed/scored counts
    """
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to index.")
        return {"indexed": 0, "failed": 0, "scored": 0, "write_blocked": True}

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    rows = _select_rows_for_indexing(
        cursor,
        library_path=library_path,
        force_reindex=force_reindex,
        limit=limit,
    )
    if not rows:
        print("No tracks to index. Use --force-reindex to rebuild embeddings.")
        conn.close()
        return {"indexed": 0, "failed": 0, "scored": 0}

    stats = _index_rows(
        rows,
        conn=conn,
        cursor=cursor,
        auto_score=auto_score,
        workers=workers,
        embed_batch=embed_batch,
    )
    conn.close()
    return stats


def index_track_ids(
    track_ids: List[str],
    *,
    force_reindex: bool = False,
    auto_score: bool = True,
    workers: int = 0,
    embed_batch: int = 0,
) -> Dict[str, int]:
    """Index a specific set of track IDs only."""
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to index.")
        return {"indexed": 0, "failed": 0, "scored": 0, "write_blocked": True}
    if not track_ids:
        return {"indexed": 0, "failed": 0, "scored": 0}

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(track_ids))
    if force_reindex:
        sql = f"SELECT track_id, filepath FROM tracks WHERE status = 'active' AND track_id IN ({placeholders})"
        cursor.execute(sql, tuple(track_ids))
    else:
        sql = f"""
            SELECT t.track_id, t.filepath
            FROM tracks t
            LEFT JOIN embeddings e ON t.track_id = e.track_id AND e.model = ?
            WHERE t.status = 'active' AND t.track_id IN ({placeholders}) AND e.track_id IS NULL
        """
        cursor.execute(sql, (MODEL_KEY, *track_ids))
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return {"indexed": 0, "failed": 0, "scored": 0}

    stats = _index_rows(
        rows,
        conn=conn,
        cursor=cursor,
        auto_score=auto_score,
        workers=workers,
        embed_batch=embed_batch,
    )
    conn.close()
    return stats


def _select_rows_for_indexing(cursor, *, library_path: Optional[str], force_reindex: bool, limit: int) -> List[tuple]:
    if library_path:
        cursor.execute(
            "SELECT track_id, filepath FROM tracks WHERE status = 'active' AND filepath LIKE ?",
            (f"{library_path}%",)
        )
        rows = cursor.fetchall()
    else:
        if force_reindex:
            cursor.execute("SELECT track_id, filepath FROM tracks WHERE status = 'active'")
        else:
            cursor.execute(
                """
                SELECT t.track_id, t.filepath
                FROM tracks t
                LEFT JOIN embeddings e ON t.track_id = e.track_id AND e.model = ?
                WHERE t.status = 'active' AND e.track_id IS NULL
                """,
                (MODEL_KEY,),
            )
        rows = cursor.fetchall()

    if limit and limit > 0:
        rows = rows[:limit]
    return rows


def _index_rows(
    rows: List[tuple],
    *,
    conn,
    cursor,
    auto_score: bool,
    workers: int,
    embed_batch: int,
) -> Dict[str, int]:
    embedder = CLAPEmbedder(model_name=MODEL_NAME, cache_dir=os.getenv("HF_HOME"), use_fallback=False)
    store = LyraChromaStore(persist_dir="./chroma_storage")

    batch_ids: List[str] = []
    batch_embeddings: List[List[float]] = []
    batch_meta: List[Dict[str, str]] = []
    indexed_ids: List[str] = []  # Track IDs we successfully indexed

    stats = {"indexed": 0, "failed": 0, "scored": 0}

    # Batch size for GPU inference â€” 8 safe for DirectML, 16-32 for CUDA 8GB+
    if workers <= 0:
        workers = auto_workers("io")
    workers = max(1, min(int(workers), 32))

    if embed_batch <= 0:
        profile = get_profile("balanced")
        if profile == "performance":
            EMBED_BATCH = 16
        elif profile == "quiet":
            EMBED_BATCH = 4
        else:
            EMBED_BATCH = 8
    else:
        EMBED_BATCH = max(1, min(int(embed_batch), 32))

    # Process rows in GPU-sized batches
    for batch_start in range(0, len(rows), EMBED_BATCH):
        wait_if_paused("index")
        batch_rows = rows[batch_start:batch_start + EMBED_BATCH]

        # Resolve existing paths
        valid_rows = []
        for track_id, filepath in batch_rows:
            path_obj = Path(filepath)
            if not path_obj.exists():
                cursor.execute(
                    "UPDATE tracks SET status = 'missing', updated_at = ? WHERE track_id = ?",
                    (time.time(), track_id)
                )
            else:
                valid_rows.append((track_id, filepath, path_obj))

        if not valid_rows:
            continue

        # Single GPU forward pass for all valid files in this batch
        paths_to_embed = [r[2] for r in valid_rows]
        embeddings_map = embedder.embed_audio_batch(paths_to_embed)

        for track_id, filepath, path_obj in valid_rows:
            embedding = embeddings_map.get(path_obj)
            if embedding is None:
                stats["failed"] += 1
                try:
                    cursor.execute(
                        "UPDATE tracks SET status = 'index_error', updated_at = ? WHERE track_id = ?",
                        (time.time(), track_id),
                    )
                except Exception:
                    pass
                try:
                    cursor.execute(
                        "INSERT INTO errors (track_id, stage, error, ts, retry_count) VALUES (?, ?, ?, ?, ?)",
                        (track_id, "embed", "Embedding failed", time.time(), 0)
                    )
                except Exception:
                    pass
                continue

            cursor.execute(
                "SELECT artist, title, album, year, genre, duration FROM tracks WHERE track_id = ?",
                (track_id,)
            )
            meta_row = cursor.fetchone()
            meta = {
                "track_id": track_id,
                "filepath": filepath,
                "artist": meta_row[0] if meta_row else "",
                "title": meta_row[1] if meta_row else "",
                "album": meta_row[2] if meta_row else "",
                "year": meta_row[3] if meta_row else "",
                "genre": meta_row[4] if meta_row else "",
                "duration": meta_row[5] if meta_row else "",
            }

            batch_ids.append(track_id)
            batch_embeddings.append(embedding.tolist())
            batch_meta.append(meta)
            indexed_ids.append(track_id)

        # Flush ChromaDB + DB records every 50 tracks
        if len(batch_ids) >= 50:
            store.batch_upsert(batch_ids, batch_embeddings, batch_meta)
            _record_embeddings(cursor, batch_ids)
            stats["indexed"] += len(batch_ids)
            batch_ids.clear()
            batch_embeddings.clear()
            batch_meta.clear()

        # Progress report
        done = min(batch_start + EMBED_BATCH, len(rows))
        logger.info(f"[INDEX] {done}/{len(rows)} embedded")

    if batch_ids:
        store.batch_upsert(batch_ids, batch_embeddings, batch_meta)
        _record_embeddings(cursor, batch_ids)
        stats["indexed"] += len(batch_ids)

    conn.commit()

    # Auto-score newly indexed tracks
    if auto_score and indexed_ids:
        logger.info(f"Auto-scoring {len(indexed_ids)} newly indexed tracks...")
        scored = _auto_score_tracks(indexed_ids, workers=workers)
        stats["scored"] = scored
        logger.info(f"Scored {scored}/{len(indexed_ids)} tracks")

    stats["workers"] = workers
    stats["embed_batch"] = EMBED_BATCH
    return stats


def _record_embeddings(cursor, track_ids: List[str]) -> None:
    now = time.time()
    for track_id in track_ids:
        cursor.execute(
            "INSERT OR REPLACE INTO embeddings (track_id, model, dimension, indexed_at) VALUES (?, ?, ?, ?)",
            (track_id, MODEL_KEY, 512, now)
        )


def _auto_score_tracks(track_ids: List[str], workers: int = 0) -> int:
    """Score a list of tracks using the dimensional scorer.

    Returns:
        Number of tracks successfully scored
    """
    try:
        from oracle.scorer import score_track, _get_embedder, _anchor_embeddings
    except ImportError:
        logger.warning("Scorer not available, skipping auto-score")
        return 0

    # Pre-warm embedder + anchor embeddings in the main thread so lru_cache is
    # populated before worker threads start. Without this, 32 threads race to
    # load the CLAP model simultaneously causing meta-tensor errors.
    try:
        _get_embedder()
        _anchor_embeddings()
    except Exception as e:
        logger.warning(f"Scorer pre-warm failed: {e}")
        return 0

    if workers <= 0:
        workers = auto_workers("cpu")
    workers = max(1, min(int(workers), 8))  # cap at 8 — scoring is GPU-bound, more = contention

    scored = 0

    def _score_one(track_id: str) -> bool:
        wait_if_paused("index:auto-score")
        result = score_track(track_id, persist=True, force=False)
        if result.get("persisted"):
            return True
        if result.get("skipped") and result.get("reason") == "already_scored":
            return True
        return False

    if workers == 1:
        for track_id in track_ids:
            try:
                if _score_one(track_id):
                    scored += 1
            except Exception as e:
                logger.debug(f"Failed to score {track_id}: {e}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_score_one, track_id) for track_id in track_ids]
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        scored += 1
                except Exception as e:
                    logger.debug(f"Failed to score track in parallel auto-score: {e}")

    return scored


def _main() -> None:
    load_dotenv(override=True)
    import argparse

    parser = argparse.ArgumentParser(description="Index library embeddings")
    parser.add_argument("--library", help="Library path scope")
    parser.add_argument("--limit", type=int, default=0, help="Limit tracks")
    parser.add_argument("--force-reindex", action="store_true", help="Force reindex")
    parser.add_argument("--no-score", action="store_true", help="Skip auto-scoring")
    parser.add_argument("--workers", type=int, default=0, help="Index workers (0=auto by profile)")
    parser.add_argument("--embed-batch", type=int, default=0, help="Embedding batch size (0=auto by profile)")
    args = parser.parse_args()

    results = index_library(
        args.library,
        limit=args.limit,
        force_reindex=args.force_reindex,
        auto_score=not args.no_score,
        workers=args.workers,
        embed_batch=args.embed_batch,
    )
    print(results)


if __name__ == "__main__":
    _main()
