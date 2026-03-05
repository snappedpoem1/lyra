from __future__ import annotations

from pathlib import Path

import oracle.api.scheduler as scheduler


def test_scheduler_lock_acquire_and_release(monkeypatch, tmp_path):
    lock_file = tmp_path / "scheduler.lock"
    monkeypatch.setenv("LYRA_SCHEDULER_LOCK_FILE", str(lock_file))

    scheduler._release_scheduler_process_lock()
    assert scheduler._acquire_scheduler_process_lock() is True
    assert lock_file.exists()

    scheduler._release_scheduler_process_lock()
    assert not lock_file.exists()


def test_scheduler_lock_refuses_existing_lock(monkeypatch, tmp_path):
    lock_file = tmp_path / "scheduler.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("pid=999999\n", encoding="utf-8")
    monkeypatch.setenv("LYRA_SCHEDULER_LOCK_FILE", str(lock_file))

    scheduler._release_scheduler_process_lock()
    acquired = scheduler._acquire_scheduler_process_lock()
    assert acquired is False
    assert lock_file.exists()
