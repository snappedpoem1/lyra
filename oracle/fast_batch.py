"""
oracle.fast_batch â€” Parallel batch acquisition + full pipeline in one pass.

Downloads tracks concurrently via ThreadPoolExecutor, then scans â†’ indexes â†’ scores
in a single pipeline run. ~4x faster than sequential for downloads.

Usage:
    from oracle.fast_batch import fast_batch
    results = fast_batch(["Heads Will Roll A-Trak Remix", "Midnight City Eric Prydz Remix"])

CLI:
    python -m oracle.fast_batch --file tracks.txt
    python -m oracle.fast_batch "query1" "query2" "query3"
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("oracle.fast_batch")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_WORKERS = 4
FAST_SLEEP_MIN = 0          # No yt-dlp inter-request sleep
FAST_SLEEP_MAX = 1          # Minimal cap
INTER_DOWNLOAD_SLEEP = 0    # No Python-level sleep between items


def _download_one(query: str, idx: int, total: int) -> dict:
    """Download a single track via yt-dlp search. Runs inside a thread."""
    from oracle.acquirers.ytdlp import YTDLPAcquirer

    # Each thread gets its own acquirer (own yt-dlp instance, own temp dir)
    acquirer = YTDLPAcquirer(staging_dir="downloads")

    tag = f"[{idx}/{total}]"
    try:
        t0 = time.perf_counter()
        if " - " in query:
            artist, title = query.split(" - ", 1)
        else:
            artist, title = "", query
        result = acquirer.download_search(artist.strip(), title.strip())
        elapsed = time.perf_counter() - t0

        if result.get("success"):
            path = result.get("path", "")
            fname = Path(path).name if path else "?"
            logger.info(f"{tag} OK  ({elapsed:.1f}s) {fname}")
            return {
                "query": query, "success": True,
                "artist": result.get("artist", ""), "title": result.get("title", ""),
                "filepath": path, "elapsed": elapsed,
            }
        else:
            err = result.get("error", "unknown error")
            logger.warning(f"{tag} FAIL ({elapsed:.1f}s) {err}")
            return {"query": query, "success": False, "error": err, "elapsed": elapsed}

    except Exception as exc:
        logger.error(f"{tag} ERROR {exc}")
        return {"query": query, "success": False, "error": str(exc), "elapsed": 0}


def fast_batch(
    queries: List[str],
    workers: int = DEFAULT_WORKERS,
    run_pipeline: bool = True,
) -> dict:
    """
    Download tracks in parallel via yt-dlp, then run scan â†’ index â†’ score.

    Args:
        queries: List of search queries (artist - title format works best).
        workers: Number of concurrent download threads.
        run_pipeline: If True, auto-run scan â†’ index â†’ score after downloads.
    Returns:
        Dict with download results and pipeline stats.
    """
    from oracle.config import load_config

    os.environ.setdefault("LYRA_WRITE_MODE", "apply_allowed")

    cfg = load_config()

    total = len(queries)
    print(f"\n{'='*60}")
    print(f"  FAST BATCH â€” {total} tracks, {workers} workers")
    print(f"  Pipeline: {'yes' if run_pipeline else 'no'}")
    print(f"{'='*60}\n")

    # â”€â”€ Phase 1: Parallel Downloads â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    t_start = time.perf_counter()
    results: List[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_one, q.strip(), i, total): q
            for i, q in enumerate(queries, 1)
            if q.strip()
        }
        for future in as_completed(futures):
            results.append(future.result())

    t_download = time.perf_counter() - t_start
    ok = sum(1 for r in results if r["success"])
    fail = total - ok

    print(f"\nâ”€â”€ Downloads: {ok}/{total} OK, {fail} failed in {t_download:.1f}s â”€â”€")

    if not ok:
        print("No tracks downloaded. Skipping pipeline.")
        return {"downloads": results, "pipeline": None, "elapsed": t_download}

    # â”€â”€ Phase 2: Pipeline (scan â†’ index â†’ score) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    pipeline_stats = {}
    if run_pipeline:
        downloads_path = str(cfg.download_dir.resolve())

        # Scan
        print("\nâ”€â”€ Scanning... â”€â”€")
        t0 = time.perf_counter()
        from oracle.scanner import scan_library
        scan_result = scan_library(downloads_path)
        t_scan = time.perf_counter() - t0
        print(f"   Scanned: {scan_result}")
        pipeline_stats["scan"] = scan_result
        pipeline_stats["scan_time"] = round(t_scan, 2)

        # Index (CLAP embeddings)
        print("â”€â”€ Indexing CLAP embeddings... â”€â”€")
        t0 = time.perf_counter()
        from oracle.indexer import index_library
        index_result = index_library(library_path=downloads_path)
        t_index = time.perf_counter() - t0
        print(f"   Indexed: {index_result}")
        pipeline_stats["index"] = index_result
        pipeline_stats["index_time"] = round(t_index, 2)

        # Score (10 dimensions)
        print("â”€â”€ Scoring dimensions... â”€â”€")
        t0 = time.perf_counter()
        from oracle.scorer import score_all
        score_result = score_all(force=False)
        t_score = time.perf_counter() - t0
        print(f"   Scored: {score_result}")
        pipeline_stats["score"] = score_result
        pipeline_stats["score_time"] = round(t_score, 2)

    t_total = time.perf_counter() - t_start

    # â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{'='*60}")
    print("  COMPLETE")
    print(f"  Downloads: {ok}/{total} in {t_download:.1f}s")
    if pipeline_stats:
        print(f"  Scan:      {pipeline_stats.get('scan_time', 0)}s")
        print(f"  Index:     {pipeline_stats.get('index_time', 0)}s")
        print(f"  Score:     {pipeline_stats.get('score_time', 0)}s")
    print(f"  Total:     {t_total:.1f}s ({t_total/60:.1f} min)")
    print(f"{'='*60}\n")

    return {
        "downloads": results,
        "pipeline": pipeline_stats,
        "ok": ok,
        "fail": fail,
        "total_time": round(t_total, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Fast parallel batch downloader + pipeline")
    parser.add_argument("queries", nargs="*", help="Search queries")
    parser.add_argument("--file", "-", help="Text file with one query per line")
    parser.add_argument("--workers", "-w", type=int, default=DEFAULT_WORKERS, help="Parallel workers (default: 4)")
    parser.add_argument("--no-pipeline", action="store_true", help="Skip scan/index/score after download")
    args = parser.parse_args()

    queries = list(args.queries)
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"File not found: {p}")
            return
        queries.extend(
            line.strip() for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if not queries:
        parser.print_help()
        return

    fast_batch(
        queries,
        workers=args.workers,
        run_pipeline=not args.no_pipeline,
    )


if __name__ == "__main__":
    _main()
