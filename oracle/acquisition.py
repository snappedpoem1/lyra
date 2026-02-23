"""Acquisition queue manager."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List
import os
import time
import logging

from dotenv import load_dotenv

from oracle.acquirers.ytdlp import YTDLPAcquirer
from oracle.acquirers import prowlarr_rd
from oracle.acquirers.guard import guard_file
from oracle.db.schema import get_connection, get_write_mode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)
MIN_GUARD_CONFIDENCE = 0.30


def _assert_guard_pass(paths: List[Path], *, stage: str) -> None:
    for path in paths:
        result = guard_file(Path(path))
        if not result.allowed:
            raise RuntimeError(
                f"Guard rejected {path.name} at {stage}: {result.rejection_reason or 'rejected'}"
            )
        if result.confidence < MIN_GUARD_CONFIDENCE:
            raise RuntimeError(
                f"Guard low confidence for {path.name} at {stage}: {result.confidence:.2f}"
            )
        logger.info(
            "[guard] %s pass: %s - %s (%.2f)",
            stage,
            result.artist,
            result.title,
            result.confidence,
        )


def enqueue_url(url: str, source: str, artist: str = "", title: str = "", album: str = "") -> None:
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to enqueue.")
        return

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO acquisition_queue (artist, title, album, url, source, status, added_at, retry_count) "
        "VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'), 0)",
        (artist, title, album, url, source)
    )
    conn.commit()
    conn.close()


def _update_status(cursor, row_id: int, status: str, error: str | None = None) -> None:
    cursor.execute(
        """
        UPDATE acquisition_queue
        SET status = ?, completed_at = datetime('now'), error = ?
        WHERE id = ?
        """,
        (status, error, row_id)
    )


def process_queue(limit: int = 0) -> Dict[str, int]:
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to process queue.")
        return {"completed": 0, "failed": 1}

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    sql = "SELECT id, url, source, retry_count FROM acquisition_queue WHERE status = 'pending' ORDER BY id DESC"
    params = ()
    if limit and limit > 0:
        sql += " LIMIT ?"
        params = (int(limit),)
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    stats = {"completed": 0, "failed": 0}

    for row_id, url, source, retry_count in rows:
        try:
            if not source or not url:
                raise RuntimeError("Queue item missing source/url")
            if source == "youtube":
                acquirer = YTDLPAcquirer()
                result = acquirer.download(url)
                if result:
                    _update_status(cursor, row_id, "completed")
                    stats["completed"] += 1
                else:
                    raise RuntimeError("yt-dlp download failed")
            elif source == "prowlarr":
                torrent_id = prowlarr_rd.add_to_real_debrid(url)
                if not torrent_id:
                    raise RuntimeError("Real-Debrid addMagnet failed")
                prowlarr_rd.select_files(torrent_id)
                max_wait = int(os.getenv("LYRA_RD_MAX_WAIT", "300"))
                info = prowlarr_rd.poll_real_debrid(torrent_id, max_wait=max_wait)
                if info.get("status") != "downloaded":
                    raise RuntimeError(f"Real-Debrid status: {info.get('status')}")
                files = prowlarr_rd.download_from_real_debrid(torrent_id)
                _assert_guard_pass(files, stage="post_download")
                staged_files = prowlarr_rd.move_to_staging(files)
                _assert_guard_pass(staged_files, stage="post_staging")
                _update_status(cursor, row_id, "completed")
                stats["completed"] += 1
            else:
                raise RuntimeError(f"Unknown source: {source}")
        except Exception as exc:
            retry_count = (retry_count or 0) + 1
            cursor.execute(
                "UPDATE acquisition_queue SET retry_count = ?, error = ? WHERE id = ?",
                (retry_count, str(exc), row_id)
            )
            if retry_count >= 3:
                _update_status(cursor, row_id, "failed", str(exc))
                stats["failed"] += 1

    conn.commit()
    conn.close()
    return stats


if __name__ == "__main__":
    load_dotenv(override=True)
    results = process_queue()
    print(results)
