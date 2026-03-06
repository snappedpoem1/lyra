from __future__ import annotations

from typing import Any

import pytest
import sqlite3
from pathlib import Path

import lyra_api
import oracle.api.blueprints.recommendations as recommendations_bp
import oracle.recommendation_broker as broker


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
            "schema_version": "2026-03-06",
            "mode": "flow",
            "novelty_band": "stretch",
            "seed_track_id": "seed-1",
            "seed_track": {"track_id": "seed-1", "artist": "Seed Artist", "title": "Seed Title"},
            "provider_weights": {"local": 0.5, "lastfm": 0.2, "listenbrainz": 0.3},
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
    monkeypatch.setattr(
        broker,
        "_recommend_from_local",
        lambda **_: (
            [
                {
                    "track": dict(shared_track),
                    "provider": "local",
                    "label": "local-flow",
                    "raw_score": 0.8,
                    "weighted_score": 0.4,
                    "reason": "Local picked it.",
                }
            ],
            {"available": True, "used": True, "weight": 0.5, "message": "ok", "matched_local_tracks": 1, "acquisition_candidates": 0},
        ),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_lastfm",
        lambda **_: (
            [
                {
                    "track": dict(shared_track),
                    "provider": "lastfm",
                    "label": "lastfm-similar-track",
                    "raw_score": 0.6,
                    "weighted_score": 0.12,
                    "reason": "Last.fm agreed.",
                }
            ],
            [],
            {"available": True, "used": True, "weight": 0.2, "message": "ok", "matched_local_tracks": 1, "acquisition_candidates": 0},
        ),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_listenbrainz",
        lambda **_: (
            [],
            [{"artist": "External Artist", "title": "External Title", "provider": "listenbrainz", "reason": "Lead", "score": 0.1}],
            {"available": True, "used": True, "weight": 0.3, "message": "ok", "matched_local_tracks": 0, "acquisition_candidates": 1},
        ),
    )

    payload = broker.recommend_tracks(
        seed_track_id=None,
        mode="flow",
        novelty_band="stretch",
        limit=6,
        provider_weights={"local": 5, "lastfm": 2, "listenbrainz": 3},
    )

    assert payload["seed_track_id"] == "seed-1"
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["track_id"] == "track-1"
    assert len(payload["candidates"][0]["provider_signals"]) == 2
    assert payload["candidates"][0]["broker_score"] == pytest.approx(0.52)
    assert payload["acquisition_candidates"][0]["provider"] == "listenbrainz"


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
        lambda **_: (
            [
                {
                    "track": dict(track_a),
                    "provider": "local",
                    "label": "local-flow",
                    "raw_score": 0.5,
                    "weighted_score": 0.3,
                    "reason": "Local picked A.",
                },
                {
                    "track": dict(track_b),
                    "provider": "local",
                    "label": "local-flow",
                    "raw_score": 0.5,
                    "weighted_score": 0.3,
                    "reason": "Local picked B.",
                },
            ],
            {"available": True, "used": True, "weight": 0.6, "message": "ok", "matched_local_tracks": 2, "acquisition_candidates": 0},
        ),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_lastfm",
        lambda **_: (
            [],
            [],
            {"available": False, "used": False, "weight": 0.2, "message": "offline", "matched_local_tracks": 0, "acquisition_candidates": 0},
        ),
    )
    monkeypatch.setattr(
        broker,
        "_recommend_from_listenbrainz",
        lambda **_: (
            [],
            [],
            {"available": False, "used": False, "weight": 0.2, "message": "offline", "matched_local_tracks": 0, "acquisition_candidates": 0},
        ),
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
