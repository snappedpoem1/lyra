from __future__ import annotations

from typing import Any

import pytest
import sqlite3
from pathlib import Path

import lyra_api
import oracle.api.blueprints.recommendations as recommendations_bp
import oracle.recommendation_broker as broker
from oracle.provider_contract import (
    Availability,
    Candidate,
    EvidenceItem,
    ProviderResult,
    ProviderStatus,
)


@pytest.fixture
def client() -> Any:
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as test_client:
        yield test_client


def test_recommendations_api_contract(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recommendations_bp,
        "recommend_tracks",
        lambda **_: {
            "schema_version": "2026-03-07",
            "mode": "flow",
            "novelty_band": "stretch",
            "seed_track_id": "seed-1",
            "seed_track": {"track_id": "seed-1", "artist": "Seed Artist", "title": "Seed Title"},
            "seed": "Seed Artist - Seed Title",
            "provider_weights": {"local": 0.5, "lastfm": 0.2, "listenbrainz": 0.3},
            "provider_reports": [
                {"provider": "local", "status": "ok", "message": "ok", "seed_context": "", "candidates": [], "errors": [], "timing_ms": 10.0},
            ],
            "recommendations": [{"track_id": "t-1", "artist": "Artist", "title": "Title"}],
            "degraded": False,
            "degradation_summary": None,
            "provider_status": {
                "local": {"available": True, "used": True, "weight": 0.5, "message": "ok"},
            },
            "candidates": [{"track_id": "t-1", "artist": "Artist", "title": "Title"}],
            "acquisition_candidates": [{"artist": "Other", "title": "Track", "provider": "listenbrainz"}],
        },
    )

    response = client.post(
        "/api/recommendations/oracle",
        json={"mode": "flow", "novelty_band": "stretch", "limit": 6},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "flow"
    assert payload["novelty_band"] == "stretch"
    assert payload["seed_track_id"] == "seed-1"
    # SPEC-004 fields
    assert "provider_reports" in payload
    assert "recommendations" in payload
    assert "degraded" in payload
    assert "degradation_summary" in payload
    # Legacy compat
    assert payload["provider_status"]["local"]["available"] is True
    assert payload["candidates"][0]["track_id"] == "t-1"


def test_recommendations_feedback_api_contract(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recommendations_bp,
        "record_feedback",
        lambda **_: {
            "status": "ok",
            "feedback_id": 7,
            "feedback_type": "accepted",
            "track_id": "t-7",
            "artist": "Artist",
            "title": "Title",
        },
    )

    response = client.post(
        "/api/recommendations/oracle/feedback",
        json={
            "feedback_type": "accepted",
            "track_id": "t-7",
            "artist": "Artist",
            "title": "Title",
            "mode": "flow",
            "novelty_band": "stretch",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["feedback_type"] == "accepted"
    assert payload["track_id"] == "t-7"


def _make_provider_result(
    provider: str,
    candidates: list[Candidate] | None = None,
    status: ProviderStatus = ProviderStatus.OK,
) -> ProviderResult:
    return ProviderResult(
        provider=provider,
        status=status,
        message=f"{provider} ready.",
        seed_context="Seed Artist - Seed Title",
        candidates=candidates or [],
        timing_ms=10.0,
    )


def test_recommendation_broker_merges_provider_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_track = {
        "track_id": "seed-1",
        "artist": "Seed Artist",
        "title": "Seed Title",
        "filepath": "C:/Music/seed.flac",
        "file_exists": True,
    }
    shared_track = {
        "track_id": "track-1",
        "artist": "Match Artist",
        "title": "Match Title",
        "filepath": "C:/Music/match.flac",
        "file_exists": True,
    }

    monkeypatch.setattr(broker, "_load_latest_track_id", lambda: "seed-1")
    monkeypatch.setattr(broker, "_load_track_from_library", lambda track_id: seed_track if track_id == "seed-1" else shared_track)
    monkeypatch.setattr(broker, "_update_health", lambda result: None)

    monkeypatch.setattr(
        broker,
        "_recommend_from_local",
        lambda **_: _make_provider_result("local", candidates=[
            Candidate(
                track_id="track-1",
                artist="Match Artist",
                title="Match Title",
                score=0.4,
                confidence=0.8,
                availability=Availability.LOCAL,
                provenance_label="local-flow",
                track_data=dict(shared_track),
                evidence=[EvidenceItem(type="embedding_neighbor", source="local", weight=0.4, text="Local picked it.")],
            ),
        ]),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_lastfm",
        lambda **_: _make_provider_result("lastfm", candidates=[
            Candidate(
                track_id="track-1",
                artist="Match Artist",
                title="Match Title",
                score=0.12,
                confidence=0.6,
                availability=Availability.LOCAL,
                provenance_label="lastfm-similar-track",
                track_data=dict(shared_track),
                evidence=[EvidenceItem(type="similar_track", source="lastfm", weight=0.12, text="Last.fm agreed.")],
            ),
        ]),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_listenbrainz",
        lambda **_: _make_provider_result("listenbrainz", candidates=[
            Candidate(
                track_id=None,
                artist="External Artist",
                title="External Title",
                score=0.1,
                confidence=0.5,
                availability=Availability.ACQUISITION_LEAD,
                provenance_label="listenbrainz-stretch",
                evidence=[EvidenceItem(type="community_popularity", source="listenbrainz", weight=0.1, text="Lead")],
            ),
        ]),
    )

    payload = broker.recommend_tracks(
        seed_track_id=None,
        mode="flow",
        novelty_band="stretch",
        limit=6,
        provider_weights={"local": 5, "lastfm": 2, "listenbrainz": 3},
    )

    # SPEC-004: schema_version is current
    assert payload["schema_version"] == "2026-03-07"
    # SPEC-004: provider_reports present
    assert len(payload["provider_reports"]) == 3
    # SPEC-004: recommendations and degraded
    assert "recommendations" in payload
    assert payload["degraded"] is False
    assert payload["degradation_summary"] is None
    # Legacy compat
    assert payload["seed_track_id"] == "seed-1"
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["track_id"] == "track-1"
    assert len(payload["candidates"][0]["provider_signals"]) == 2
    assert payload["candidates"][0]["broker_score"] == pytest.approx(0.52)
    # Evidence preserved from both providers
    assert len(payload["candidates"][0]["evidence"]) == 2
    # Acquisition leads
    assert payload["acquisition_candidates"][0]["provider"] == "listenbrainz"


def test_recommendation_broker_degradation_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_track = {
        "track_id": "seed-1",
        "artist": "Seed Artist",
        "title": "Seed Title",
        "filepath": "C:/Music/seed.flac",
        "file_exists": True,
    }

    monkeypatch.setattr(broker, "_load_latest_track_id", lambda: "seed-1")
    monkeypatch.setattr(broker, "_load_track_from_library", lambda track_id: seed_track)
    monkeypatch.setattr(broker, "_update_health", lambda result: None)

    monkeypatch.setattr(
        broker,
        "_recommend_from_local",
        lambda **_: _make_provider_result("local", candidates=[
            Candidate(
                track_id="track-1", artist="A", title="T",
                score=0.5, confidence=0.9, availability=Availability.LOCAL,
                provenance_label="local-flow",
                track_data={"track_id": "track-1", "artist": "A", "title": "T", "file_exists": True},
                evidence=[EvidenceItem(type="embedding_neighbor", source="local", weight=0.5, text="Flow match.")],
            ),
        ]),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_lastfm",
        lambda **_: ProviderResult(
            provider="lastfm",
            status=ProviderStatus.FAILED,
            message="LASTFM_API_KEY is not configured.",
            seed_context="Seed Artist - Seed Title",
            errors=[],
            timing_ms=0.5,
        ),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_listenbrainz",
        lambda **_: ProviderResult(
            provider="listenbrainz",
            status=ProviderStatus.EMPTY,
            message="No data.",
            seed_context="Seed Artist - Seed Title",
            timing_ms=200.0,
        ),
    )

    payload = broker.recommend_tracks(
        seed_track_id="seed-1",
        mode="flow",
        novelty_band="stretch",
        limit=6,
    )

    assert payload["degraded"] is True
    assert "lastfm" in payload["degradation_summary"]
    # Provider reports show individual status
    by_provider = {r["provider"]: r for r in payload["provider_reports"]}
    assert by_provider["local"]["status"] == "ok"
    assert by_provider["lastfm"]["status"] == "failed"
    assert by_provider["listenbrainz"]["status"] == "empty"


def test_recommendation_broker_feedback_bias_reorders_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "feedback.db"

    def _connect(timeout: float = 5.0) -> sqlite3.Connection:
        del timeout
        return sqlite3.connect(db_path)

    monkeypatch.setattr(broker, "get_connection", _connect)
    monkeypatch.setattr(broker, "get_write_mode", lambda: "apply_allowed")
    monkeypatch.setattr(broker, "_update_health", lambda result: None)

    seed_track = {
        "track_id": "seed-1",
        "artist": "Seed Artist",
        "title": "Seed Title",
        "filepath": "C:/Music/seed.flac",
        "file_exists": True,
    }
    track_a = {
        "track_id": "track-a",
        "artist": "Artist A",
        "title": "Title A",
        "filepath": "C:/Music/a.flac",
        "file_exists": True,
    }
    track_b = {
        "track_id": "track-b",
        "artist": "Artist B",
        "title": "Title B",
        "filepath": "C:/Music/b.flac",
        "file_exists": True,
    }
    track_map = {
        "seed-1": seed_track,
        "track-a": track_a,
        "track-b": track_b,
    }

    monkeypatch.setattr(broker, "_load_latest_track_id", lambda: "seed-1")
    monkeypatch.setattr(broker, "_load_track_from_library", lambda track_id: track_map.get(track_id))

    monkeypatch.setattr(
        broker,
        "_recommend_from_local",
        lambda **_: _make_provider_result("local", candidates=[
            Candidate(
                track_id="track-a", artist="Artist A", title="Title A",
                score=0.3, confidence=0.5, availability=Availability.LOCAL,
                provenance_label="local-flow", track_data=dict(track_a),
                evidence=[EvidenceItem(type="embedding_neighbor", source="local", weight=0.3, text="Local picked A.")],
            ),
            Candidate(
                track_id="track-b", artist="Artist B", title="Title B",
                score=0.3, confidence=0.5, availability=Availability.LOCAL,
                provenance_label="local-flow", track_data=dict(track_b),
                evidence=[EvidenceItem(type="embedding_neighbor", source="local", weight=0.3, text="Local picked B.")],
            ),
        ]),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_lastfm",
        lambda **_: _make_provider_result("lastfm", status=ProviderStatus.FAILED),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_listenbrainz",
        lambda **_: _make_provider_result("listenbrainz", status=ProviderStatus.FAILED),
    )

    broker.record_feedback(
        feedback_type="accepted",
        track_id="track-a",
        artist="Artist A",
        title="Title A",
        mode="flow",
        novelty_band="stretch",
        provider="local",
    )
    broker.record_feedback(
        feedback_type="skipped",
        track_id="track-b",
        artist="Artist B",
        title="Title B",
        mode="flow",
        novelty_band="stretch",
        provider="local",
    )

    payload = broker.recommend_tracks(
        seed_track_id="seed-1",
        mode="flow",
        novelty_band="stretch",
        limit=6,
        provider_weights={"local": 1.0, "lastfm": 0.0, "listenbrainz": 0.0},
    )

    assert payload["candidates"][0]["track_id"] == "track-a"
    assert payload["candidates"][0]["feedback_bias"] > 0
    assert payload["candidates"][1]["track_id"] == "track-b"
    assert payload["candidates"][1]["feedback_bias"] < 0


def test_provider_health_endpoint(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recommendations_bp,
        "get_all_health",
        lambda: [
            {"provider": "local", "enabled": True, "status": "healthy"},
            {"provider": "lastfm", "enabled": True, "status": "unavailable"},
        ],
    )
    response = client.get("/api/recommendations/providers/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert "providers" in payload
    assert len(payload["providers"]) == 2
