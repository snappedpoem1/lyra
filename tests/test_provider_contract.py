"""Tests for the normalized provider contract (SPEC-004)."""

from __future__ import annotations

from typing import Any

import pytest

from oracle.provider_contract import (
    BROKER_SCHEMA_VERSION,
    Availability,
    Candidate,
    EvidenceItem,
    ProviderError,
    ProviderHealth,
    ProviderResult,
    ProviderStatus,
    ProviderTimer,
    HealthStatus,
)
from oracle.provider_health import get_all_health, reset, update_from_result
from oracle.doctor import _check_recommendation_providers, CheckResult


class TestEvidenceItem:
    def test_to_dict_basic(self) -> None:
        e = EvidenceItem(type="similar_track", source="lastfm", weight=0.42, text="Similar to X.")
        d = e.to_dict()
        assert d["type"] == "similar_track"
        assert d["source"] == "lastfm"
        assert d["weight"] == 0.42
        assert d["text"] == "Similar to X."
        assert "raw_value" not in d

    def test_to_dict_with_raw_value(self) -> None:
        e = EvidenceItem(
            type="community_popularity",
            source="listenbrainz",
            weight=0.3,
            text="Popular.",
            raw_value={"listen_count": 1200},
        )
        d = e.to_dict()
        assert d["raw_value"] == {"listen_count": 1200}


class TestCandidate:
    def test_to_dict_minimal(self) -> None:
        c = Candidate(track_id="t-1", artist="Artist", title="Title")
        d = c.to_dict()
        assert d["track_id"] == "t-1"
        assert d["artist"] == "Artist"
        assert d["availability"] == "unresolved"
        assert d["evidence"] == []
        assert d["confidence"] == 0.0

    def test_to_dict_with_evidence(self) -> None:
        c = Candidate(
            track_id="t-2",
            artist="A",
            title="T",
            score=0.55,
            confidence=0.8,
            novelty_band_fit="stretch",
            availability=Availability.LOCAL,
            provenance_label="local-flow",
            evidence=[
                EvidenceItem(type="embedding_neighbor", source="local", weight=0.55, text="Flow match."),
            ],
        )
        d = c.to_dict()
        assert d["score"] == 0.55
        assert d["confidence"] == 0.8
        assert d["availability"] == "local"
        assert len(d["evidence"]) == 1
        assert d["evidence"][0]["type"] == "embedding_neighbor"

    def test_acquisition_lead_has_no_track_id(self) -> None:
        c = Candidate(
            track_id=None,
            artist="New",
            title="Track",
            availability=Availability.ACQUISITION_LEAD,
        )
        d = c.to_dict()
        assert d["track_id"] is None
        assert d["availability"] == "acquisition-lead"


class TestProviderResult:
    def test_ok_result(self) -> None:
        r = ProviderResult(
            provider="local",
            status=ProviderStatus.OK,
            message="Ready.",
            seed_context="Artist - Title",
            candidates=[Candidate(track_id="t-1", artist="A", title="T")],
            timing_ms=42.5,
        )
        d = r.to_dict()
        assert d["provider"] == "local"
        assert d["status"] == "ok"
        assert d["timing_ms"] == 42.5
        assert len(d["candidates"]) == 1
        assert d["errors"] == []

    def test_failed_result_with_errors(self) -> None:
        r = ProviderResult(
            provider="lastfm",
            status=ProviderStatus.FAILED,
            message="API key missing.",
            errors=[ProviderError(code="not_configured", message="LASTFM_API_KEY is not set.")],
            timing_ms=1.2,
        )
        d = r.to_dict()
        assert d["status"] == "failed"
        assert len(d["errors"]) == 1
        assert d["errors"][0]["code"] == "not_configured"
        assert d["candidates"] == []

    def test_empty_result(self) -> None:
        r = ProviderResult(
            provider="listenbrainz",
            status=ProviderStatus.EMPTY,
            message="No data.",
            timing_ms=200.0,
        )
        d = r.to_dict()
        assert d["status"] == "empty"
        assert d["candidates"] == []


class TestProviderTimer:
    def test_timer_measures_elapsed(self) -> None:
        with ProviderTimer() as t:
            total = sum(range(1000))
        assert t.elapsed_ms > 0
        assert total == 499500


class TestProviderHealth:
    def test_record_success(self) -> None:
        h = ProviderHealth(provider="local")
        h.record_success()
        assert h.status == HealthStatus.HEALTHY
        assert h.last_success_at is not None

    def test_record_error(self) -> None:
        h = ProviderHealth(provider="lastfm")
        h.record_error("timeout")
        assert h.status == HealthStatus.DEGRADED
        assert h.last_error_summary == "timeout"

    def test_record_failure(self) -> None:
        h = ProviderHealth(provider="listenbrainz")
        h.record_failure("API down")
        assert h.status == HealthStatus.UNAVAILABLE

    def test_to_dict(self) -> None:
        h = ProviderHealth(provider="local", enabled=True)
        d = h.to_dict()
        assert d["provider"] == "local"
        assert d["enabled"] is True
        assert d["status"] == "healthy"


class TestProviderHealthRegistry:
    def setup_method(self) -> None:
        reset()

    def test_update_from_ok_result(self) -> None:
        r = ProviderResult(provider="local", status=ProviderStatus.OK, message="ok")
        update_from_result(r)
        health = get_all_health()
        assert len(health) == 1
        assert health[0]["provider"] == "local"
        assert health[0]["status"] == "healthy"

    def test_update_from_failed_result(self) -> None:
        r = ProviderResult(provider="lastfm", status=ProviderStatus.FAILED, message="no key")
        update_from_result(r)
        health = get_all_health()
        assert any(h["provider"] == "lastfm" and h["status"] == "unavailable" for h in health)

    def test_multiple_providers(self) -> None:
        update_from_result(ProviderResult(provider="local", status=ProviderStatus.OK, message="ok"))
        update_from_result(ProviderResult(provider="lastfm", status=ProviderStatus.EMPTY, message="empty"))
        update_from_result(ProviderResult(provider="listenbrainz", status=ProviderStatus.FAILED, message="down"))
        health = get_all_health()
        assert len(health) == 3
        by_provider = {h["provider"]: h for h in health}
        assert by_provider["local"]["status"] == "healthy"
        assert by_provider["lastfm"]["status"] == "healthy"  # empty is still success
        assert by_provider["listenbrainz"]["status"] == "unavailable"

    def test_structured_logging_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        with caplog.at_level(logging.WARNING, logger="oracle.provider_health"):
            update_from_result(ProviderResult(
                provider="lastfm", status=ProviderStatus.FAILED,
                message="API timeout", timing_ms=5000.0,
            ))
        assert any("lastfm" in r.message and "failed" in r.message for r in caplog.records)

    def test_structured_logging_on_recovery(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        # First make it fail
        update_from_result(ProviderResult(
            provider="lastfm", status=ProviderStatus.FAILED, message="down", timing_ms=100.0,
        ))
        # Then recover
        with caplog.at_level(logging.INFO, logger="oracle.provider_health"):
            update_from_result(ProviderResult(
                provider="lastfm", status=ProviderStatus.OK, message="ok", timing_ms=50.0,
            ))
        assert any("recovered" in r.message and "lastfm" in r.message for r in caplog.records)


class TestDoctorProviderChecks:
    def setup_method(self) -> None:
        reset()

    def test_no_health_data_returns_warning(self) -> None:
        results = _check_recommendation_providers()
        assert len(results) == 1
        assert results[0].status == "WARNING"
        assert "not run" in results[0].details.lower() or "no provider" in results[0].details.lower()

    def test_healthy_provider_returns_pass(self) -> None:
        update_from_result(ProviderResult(provider="local", status=ProviderStatus.OK, message="ok"))
        results = _check_recommendation_providers()
        assert any(r.name == "Provider (local)" and r.status == "PASS" for r in results)

    def test_failed_provider_returns_fail(self) -> None:
        update_from_result(ProviderResult(provider="lastfm", status=ProviderStatus.FAILED, message="no key"))
        results = _check_recommendation_providers()
        assert any(r.name == "Provider (lastfm)" and r.status == "FAIL" for r in results)

    def test_mixed_providers(self) -> None:
        update_from_result(ProviderResult(provider="local", status=ProviderStatus.OK, message="ok"))
        update_from_result(ProviderResult(provider="lastfm", status=ProviderStatus.FAILED, message="no key"))
        update_from_result(ProviderResult(provider="listenbrainz", status=ProviderStatus.EMPTY, message="empty"))
        results = _check_recommendation_providers()
        by_name = {r.name: r for r in results}
        assert by_name["Provider (local)"].status == "PASS"
        assert by_name["Provider (lastfm)"].status == "FAIL"
        assert by_name["Provider (listenbrainz)"].status == "PASS"
