"""Acquisition tier availability bootstrap snapshot."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "status": "pending",
    "docker_required": False,
    "checked_at": None,
    "elapsed_ms": None,
    "tiers": {},
    "available_tiers": 0,
    "total_tiers": 0,
    "error": None,
}
_THREAD_STARTED = False


def _build_summary(tiers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_tiers = len(tiers)
    available_tiers = sum(1 for tier in tiers.values() if bool(tier.get("available")))
    return {
        "status": "ok",
        "docker_required": False,
        "checked_at": time.time(),
        "tiers": tiers,
        "available_tiers": available_tiers,
        "total_tiers": total_tiers,
        "error": None,
    }


def _update_state(snapshot: dict[str, Any]) -> None:
    with _LOCK:
        _STATE.update(snapshot)


def get_snapshot() -> dict[str, Any]:
    """Return the latest acquisition bootstrap snapshot."""
    with _LOCK:
        return dict(_STATE)


def refresh_snapshot() -> dict[str, Any]:
    """Refresh tier availability snapshot without booting external services."""
    started_at = time.perf_counter()
    try:
        from oracle.acquirers.waterfall import get_tier_status

        tiers = get_tier_status()
        snapshot = _build_summary(tiers)
        snapshot["elapsed_ms"] = int((time.perf_counter() - started_at) * 1000)
        _update_state(snapshot)
        return snapshot
    except Exception as exc:  # noqa: BLE001
        logger.warning("[acquisition-bootstrap] tier status refresh failed: %s", exc)
        failure_snapshot = {
            "status": "degraded",
            "docker_required": False,
            "checked_at": time.time(),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            "tiers": {},
            "available_tiers": 0,
            "total_tiers": 0,
            "error": str(exc),
        }
        _update_state(failure_snapshot)
        return failure_snapshot


def start_background_refresh() -> None:
    """Run one background snapshot refresh if not already started."""
    global _THREAD_STARTED

    with _LOCK:
        if _THREAD_STARTED:
            return
        _THREAD_STARTED = True

    def _runner() -> None:
        refresh_snapshot()

    thread = threading.Thread(target=_runner, name="acquisition-bootstrap-refresh", daemon=True)
    thread.start()
