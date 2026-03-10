"""Tests for POST /api/spotify/import and GET /api/spotify/import/status."""

from __future__ import annotations

import time
import threading
import pytest
import oracle.api.blueprints.acquire as acquire_bp


@pytest.fixture(autouse=True)
def _reset_import_state():
    """Reset global import state before each test."""
    acquire_bp._spotify_import_state.update(
        running=False, last_result=None, last_error=None, started_at=None
    )
    if acquire_bp._spotify_import_lock.locked():
        try:
            acquire_bp._spotify_import_lock.release()
        except RuntimeError:
            pass
    yield
    acquire_bp._spotify_import_state.update(
        running=False, last_result=None, last_error=None, started_at=None
    )


@pytest.fixture()
def app():
    import lyra_api
    application = lyra_api.create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def test_import_starts_and_returns_started(client, monkeypatch):
    """POST /api/spotify/import should return {ok: true, status: 'started'}."""
    called = []

    def _fake_import():
        called.append(True)
        acquire_bp._spotify_import_state["last_result"] = {"files": 9, "streams": 127572, "skipped": 51, "errors": 0}
        acquire_bp._spotify_import_state["running"] = False

    monkeypatch.setattr(acquire_bp, "_run_spotify_import_background", _fake_import)

    resp = client.post("/api/spotify/import")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "started"


def test_import_conflict_while_running(client, monkeypatch):
    """Second POST while import is running should return 409."""
    acquire_bp._spotify_import_state["running"] = True

    resp = client.post("/api/spotify/import")
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["ok"] is False
    assert "already in progress" in data["error"]


def test_import_status_idle(client):
    """GET /api/spotify/import/status when idle returns running=False."""
    resp = client.get("/api/spotify/import/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["running"] is False
    assert data["last_result"] is None
    assert data["last_error"] is None


def test_import_status_after_success(client, monkeypatch):
    """Status endpoint reflects last_result after a completed import."""
    acquire_bp._spotify_import_state["last_result"] = {
        "files": 9, "streams": 127572, "skipped": 51, "errors": 0
    }
    acquire_bp._spotify_import_state["running"] = False

    resp = client.get("/api/spotify/import/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["last_result"]["streams"] == 127572
    assert data["running"] is False


def test_import_status_after_failure(client):
    """Status endpoint reflects last_error after a failed import."""
    acquire_bp._spotify_import_state["last_error"] = "spotify_import.py not found"
    acquire_bp._spotify_import_state["running"] = False

    resp = client.get("/api/spotify/import/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "not found" in data["last_error"]
    assert data["last_result"] is None


def test_import_thread_runs_background_fn(monkeypatch):
    """_run_spotify_import_background sets last_result and clears running flag."""
    results = []
    monkeypatch.setattr(
        "oracle.importers.run_spotify_history_import",
        lambda: {"files": 3, "streams": 1000, "skipped": 0, "errors": 0},
        raising=False,
    )

    acquire_bp._spotify_import_state["running"] = True
    acquire_bp._run_spotify_import_background()

    assert acquire_bp._spotify_import_state["running"] is False
    assert acquire_bp._spotify_import_state["last_result"]["streams"] == 1000
    assert acquire_bp._spotify_import_state["last_error"] is None


def test_import_thread_sets_error_on_exception(monkeypatch):
    """_run_spotify_import_background captures exceptions into last_error."""
    def _boom():
        raise RuntimeError("no history files found")

    monkeypatch.setattr(
        "oracle.importers.run_spotify_history_import",
        _boom,
        raising=False,
    )

    acquire_bp._spotify_import_state["running"] = True
    acquire_bp._run_spotify_import_background()

    assert acquire_bp._spotify_import_state["running"] is False
    assert acquire_bp._spotify_import_state["last_result"] is None
    assert "no history files" in acquire_bp._spotify_import_state["last_error"]
