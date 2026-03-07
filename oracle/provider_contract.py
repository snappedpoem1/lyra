"""Normalized provider contract types for the recommendation broker.

Implements SPEC-004: Recommendation Provider Contract and Evidence Payload.
Every provider adapter returns a ProviderResult with normalized candidates,
structured evidence, timing, and explicit degradation state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    DEGRADED = "degraded"
    FAILED = "failed"


class Availability(str, Enum):
    LOCAL = "local"
    ACQUISITION_LEAD = "acquisition-lead"
    UNRESOLVED = "unresolved"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass
class EvidenceItem:
    """One machine-readable piece of recommendation evidence."""

    type: str
    source: str
    weight: float
    text: str
    raw_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "source": self.source,
            "weight": round(self.weight, 4),
            "text": self.text,
        }
        if self.raw_value is not None:
            d["raw_value"] = self.raw_value
        return d


@dataclass
class Candidate:
    """One normalized recommendation candidate from a provider."""

    track_id: str | None
    artist: str
    title: str
    album: str | None = None
    external_identity: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    confidence: float = 0.0
    novelty_band_fit: str = "stretch"
    evidence: list[EvidenceItem] = field(default_factory=list)
    provenance_label: str = ""
    availability: Availability = Availability.UNRESOLVED
    # Enriched track data for local matches
    track_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "external_identity": self.external_identity,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "novelty_band_fit": self.novelty_band_fit,
            "evidence": [e.to_dict() for e in self.evidence],
            "provenance_label": self.provenance_label,
            "availability": self.availability.value,
        }


@dataclass
class ProviderError:
    """Structured error from a provider."""

    code: str
    message: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class ProviderResult:
    """Normalized result from one provider adapter."""

    provider: str
    status: ProviderStatus
    message: str
    seed_context: str = ""
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[ProviderError] = field(default_factory=list)
    timing_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "message": self.message,
            "seed_context": self.seed_context,
            "candidates": [c.to_dict() for c in self.candidates],
            "errors": [e.to_dict() for e in self.errors],
            "timing_ms": round(self.timing_ms, 1),
        }


@dataclass
class ProviderHealth:
    """Provider health summary per SPEC-006."""

    provider: str
    enabled: bool = True
    status: HealthStatus = HealthStatus.HEALTHY
    last_success_at: float | None = None
    last_error_at: float | None = None
    last_error_summary: str | None = None
    rate_limit_state: str | None = None
    cache_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "status": self.status.value,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error_summary": self.last_error_summary,
            "rate_limit_state": self.rate_limit_state,
            "cache_state": self.cache_state,
        }

    def record_success(self) -> None:
        self.last_success_at = time.time()
        self.status = HealthStatus.HEALTHY

    def record_error(self, summary: str) -> None:
        self.last_error_at = time.time()
        self.last_error_summary = summary
        self.status = HealthStatus.DEGRADED

    def record_failure(self, summary: str) -> None:
        self.last_error_at = time.time()
        self.last_error_summary = summary
        self.status = HealthStatus.UNAVAILABLE


class ProviderTimer:
    """Context manager for timing provider calls."""

    def __init__(self) -> None:
        self.start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ProviderTimer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000.0


# Schema version for the broker output contract
BROKER_SCHEMA_VERSION = "2026-03-07"
