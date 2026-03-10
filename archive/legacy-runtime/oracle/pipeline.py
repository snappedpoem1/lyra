"""Compatibility pipeline wrapper.

This module keeps legacy pipeline commands callable while routing acquisition work
through the authoritative smart pipeline + waterfall stack.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from oracle.acquirers.smart_pipeline import AcquisitionRequest, SmartAcquisition
from oracle.config import LIBRARY_BASE, get_connection

logger = logging.getLogger(__name__)


class PipelineState:
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineJob:
    job_id: str
    query: str
    state: str
    created_at: str
    updated_at: str
    result_json: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.result_json:
            try:
                payload["result"] = json.loads(self.result_json)
            except json.JSONDecodeError:
                payload["result"] = {"raw": self.result_json}
        return payload


class Pipeline:
    """Legacy-compatible pipeline facade over SmartAcquisition."""

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(timeout=10.0)
        try:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_jobs (
                    job_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )
            c.execute("PRAGMA table_info(pipeline_jobs)")
            columns = {row[1] for row in c.fetchall()}
            if "result_json" not in columns:
                c.execute("ALTER TABLE pipeline_jobs ADD COLUMN result_json TEXT")
            if "error" not in columns:
                c.execute("ALTER TABLE pipeline_jobs ADD COLUMN error TEXT")
            conn.commit()
        finally:
            conn.close()

    def create_job(self, query: str) -> str:
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{random.randint(1000, 9999)}"
        timestamp = datetime.now().isoformat()

        conn = get_connection(timeout=10.0)
        try:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO pipeline_jobs (job_id, query, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, query, PipelineState.REQUESTED, timestamp, timestamp),
            )
            conn.commit()
            return job_id
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(timeout=10.0)
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT job_id, query, state, created_at, updated_at, result_json, error
                FROM pipeline_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            )
            row = c.fetchone()
            if not row:
                return None
            return PipelineJob(*row).to_dict()
        finally:
            conn.close()

    def update_job(self, job_id: str, state: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        timestamp = datetime.now().isoformat()
        result_json = json.dumps(result) if result is not None else None

        conn = get_connection(timeout=10.0)
        try:
            c = conn.cursor()
            c.execute(
                """
                UPDATE pipeline_jobs
                SET state = ?, updated_at = ?, result_json = COALESCE(?, result_json), error = ?
                WHERE job_id = ?
                """,
                (state, timestamp, result_json, error, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = get_connection(timeout=10.0)
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT job_id, query, state, created_at, updated_at, result_json, error
                FROM pipeline_jobs
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [PipelineJob(*row).to_dict() for row in c.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _parse_query(query: str) -> Tuple[str, str]:
        cleaned = query.strip()
        if " - " in cleaned:
            artist, title = cleaned.split(" - ", 1)
            return artist.strip(), title.strip()
        if " by " in cleaned.lower():
            parts = cleaned.rsplit(" by ", 1)
            return parts[1].strip(), parts[0].strip()
        return "Unknown Artist", cleaned

    def run(self, query_or_job_id: str) -> Dict[str, Any]:
        existing = self.get_job(query_or_job_id)
        if existing:
            query = existing["query"]
            job_id = query_or_job_id
            state = existing.get("state")
            if state == PipelineState.COMPLETED:
                logger.info("Pipeline job %s already completed; returning cached result", job_id)
                return existing
            if state == PipelineState.RUNNING:
                logger.info("Pipeline job %s is already running; returning current status", job_id)
                return existing
            logger.info("Resuming pipeline job %s from state=%s", job_id, state)
        else:
            query = query_or_job_id
            job_id = self.create_job(query)

        self.update_job(job_id, PipelineState.RUNNING)
        artist, title = self._parse_query(query)

        pipeline = SmartAcquisition(library_path=LIBRARY_BASE, require_validation=True)
        try:
            result = pipeline.acquire(
                AcquisitionRequest(
                    artist=artist,
                    title=title,
                    source="pipeline",
                )
            )
            payload = {
                "job_id": job_id,
                "query": query,
                "artist": artist,
                "title": title,
                "success": result.success,
                "filepath": str(result.filepath) if result.filepath else None,
                "quality": result.quality,
                "tier_used": result.tier_used,
                "rejection_reason": result.rejection_reason,
                "elapsed": result.elapsed,
            }
            state = PipelineState.COMPLETED if result.success else PipelineState.FAILED
            self.update_job(job_id, state, result=payload, error=result.rejection_reason)
            return self.get_job(job_id) or payload
        finally:
            pipeline.close()

    def start_acquisition(self, query: str) -> Dict[str, Any]:
        """Deprecated compatibility wrapper."""
        logger.warning("[DEPRECATED] Pipeline.start_acquisition() now creates a queued compatibility job only.")
        job_id = self.create_job(query)
        return self.get_job(job_id) or {"job_id": job_id, "query": query}

    def run_pipeline(self, job_id_or_query: str) -> Dict[str, Any]:
        """Deprecated compatibility wrapper."""
        logger.warning("[DEPRECATED] Pipeline.run_pipeline() delegates to Pipeline.run().")
        return self.run(job_id_or_query)


_pipeline: Optional[Pipeline] = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


def start_acquisition(query: str) -> str:
    logger.warning("[DEPRECATED] start_acquisition() delegates to compatibility pipeline facade.")
    return get_pipeline().create_job(query)


def run_pipeline(job_id_or_query: str) -> Dict[str, Any]:
    logger.warning("[DEPRECATED] run_pipeline() delegates to compatibility pipeline facade.")
    return get_pipeline().run(job_id_or_query)


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return get_pipeline().get_job(job_id)


def list_recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    return get_pipeline().list_jobs(limit)


def main() -> int:
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m oracle.pipeline <run|status|list> [...]")
        return 1

    command = sys.argv[1]
    pipeline = get_pipeline()

    if command == "run":
        if len(sys.argv) < 3:
            print("Usage: python -m oracle.pipeline run <query>")
            return 1
        query = " ".join(sys.argv[2:])
        result = pipeline.run(query)
        print(json.dumps(result, indent=2))
        return 0

    if command == "status":
        if len(sys.argv) < 3:
            print("Usage: python -m oracle.pipeline status <job_id>")
            return 1
        print(json.dumps(pipeline.get_job(sys.argv[2]), indent=2))
        return 0

    if command == "list":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(json.dumps(pipeline.list_jobs(n), indent=2))
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
