"""Provider health registry per SPEC-006.

Tracks provider health state in memory with structured summaries
available to diagnostics, doctor, and API consumers.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from oracle.provider_contract import HealthStatus, ProviderHealth, ProviderResult, ProviderStatus

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_registry: dict[str, ProviderHealth] = {}


def _ensure_provider(provider: str) -> ProviderHealth:
    """Return or create the health entry for a provider."""
    if provider not in _registry:
        _registry[provider] = ProviderHealth(provider=provider)
    return _registry[provider]


def update_from_result(result: ProviderResult) -> None:
    """Update health state from a provider result."""
    with _lock:
        health = _ensure_provider(result.provider)
        if result.status == ProviderStatus.OK:
            health.record_success()
        elif result.status == ProviderStatus.EMPTY:
            health.record_success()
        elif result.status == ProviderStatus.DEGRADED:
            health.record_error(result.message)
        elif result.status == ProviderStatus.FAILED:
            health.record_failure(result.message)


def get_health(provider: str) -> ProviderHealth | None:
    """Return the health entry for a provider, or None if unknown."""
    with _lock:
        return _registry.get(provider)


def get_all_health() -> list[dict[str, Any]]:
    """Return health summaries for all known providers."""
    with _lock:
        return [h.to_dict() for h in _registry.values()]


def reset() -> None:
    """Clear all health state (useful for testing)."""
    with _lock:
        _registry.clear()
