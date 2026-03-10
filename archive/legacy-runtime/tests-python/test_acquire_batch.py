from __future__ import annotations

from types import SimpleNamespace

import oracle.api.blueprints.acquire as acquire_bp
import oracle.fast_batch as fast_batch


def _drain_events(job_id: str) -> list[dict]:
    events: list[dict] = []
    q = acquire_bp._batch_queues[job_id]
    while True:
        msg = q.get(timeout=1)
        if msg is None:
            break
        events.append(msg)
    return events


def test_run_batch_job_pipeline_success(monkeypatch, tmp_path):
    job_id = "batch-success"
    acquire_bp._batch_jobs.clear()
    acquire_bp._batch_queues.clear()
    acquire_bp._batch_jobs[job_id] = {"status": "running", "total": 1}
    acquire_bp._batch_queues[job_id] = __import__("queue").Queue()

    monkeypatch.setattr(
        fast_batch,
        "_download_one",
        lambda query, idx, total: {
            "success": True,
            "artist": "A",
            "title": "T",
            "elapsed": 0.01,
            "path": str(tmp_path / "a.flac"),
        },
    )
    monkeypatch.setattr(acquire_bp, "load_config", lambda: SimpleNamespace(download_dir=tmp_path))
    monkeypatch.setattr("oracle.scanner.scan_library", lambda path: {"scanned": 1})
    monkeypatch.setattr("oracle.indexer.index_library", lambda library_path: {"indexed": 1})
    monkeypatch.setattr("oracle.scorer.score_all", lambda force=False: {"scored": 1})

    acquire_bp._run_batch_job(job_id, ["A - T"], workers=1, run_pipeline=True)

    job = acquire_bp._batch_jobs[job_id]
    assert job["status"] == "complete"
    assert job["ok"] == 1
    assert job["fail"] == 0

    events = _drain_events(job_id)
    names = [event.get("event") for event in events]
    assert "pipeline" in names
    assert "complete" in names
    assert "error" not in names


def test_run_batch_job_pipeline_failure_marks_failed(monkeypatch):
    job_id = "batch-fail"
    acquire_bp._batch_jobs.clear()
    acquire_bp._batch_queues.clear()
    acquire_bp._batch_jobs[job_id] = {"status": "running", "total": 1}
    acquire_bp._batch_queues[job_id] = __import__("queue").Queue()

    monkeypatch.setattr(
        fast_batch,
        "_download_one",
        lambda query, idx, total: {
            "success": True,
            "artist": "A",
            "title": "T",
            "elapsed": 0.01,
        },
    )
    monkeypatch.setattr(acquire_bp, "load_config", lambda: (_ for _ in ()).throw(RuntimeError("config exploded")))

    acquire_bp._run_batch_job(job_id, ["A - T"], workers=1, run_pipeline=True)

    job = acquire_bp._batch_jobs[job_id]
    assert job["status"] == "failed"
    assert "config exploded" in job["error"]

    events = _drain_events(job_id)
    names = [event.get("event") for event in events]
    assert "error" in names
    assert "complete" in names
