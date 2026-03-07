"""Tests for Wave 9: Scout cross-genre bridge and LB community weather providers.

Covers:
- _scout_bridge_genre() helper
- _recommend_from_scout() provider
- _recommend_from_listenbrainz_weather() provider
- DEFAULT_PROVIDER_WEIGHTS keys and sum
- get_similar_artists_recordings() edge cases
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import oracle.recommendation_broker as broker
from oracle.integrations import listenbrainz as lb_module
from oracle.provider_contract import (
    Availability,
    EvidenceItem,
    ProviderStatus,
)


# ---------------------------------------------------------------------------
# _scout_bridge_genre
# ---------------------------------------------------------------------------

def test_scout_bridge_genre_flow_returns_first_adjacent() -> None:
    result = broker._scout_bridge_genre("rock", "flow")
    assert result == "electronic"


def test_scout_bridge_genre_known_seed_flow_not_same_as_seed() -> None:
    result = broker._scout_bridge_genre("jazz", "flow")
    assert result != "jazz"


def test_scout_bridge_genre_chaos_returns_valid_genre() -> None:
    result = broker._scout_bridge_genre("rock", "chaos")
    # Should be one of rock's bridges or a known genre string
    assert isinstance(result, str)
    assert len(result) > 0


def test_scout_bridge_genre_discovery_returns_string() -> None:
    result = broker._scout_bridge_genre("electronic", "discovery")
    assert isinstance(result, str)


def test_scout_bridge_genre_unknown_seed_falls_back() -> None:
    # Seed not in map — should still return a non-empty string
    result = broker._scout_bridge_genre("xyzzy", "flow")
    assert isinstance(result, str)
    assert len(result) > 0


def test_scout_bridge_genre_empty_seed_returns_string() -> None:
    # Edge: completely empty string — fallback picks any known genre
    result = broker._scout_bridge_genre("", "flow")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# DEFAULT_PROVIDER_WEIGHTS
# ---------------------------------------------------------------------------

def test_default_provider_weights_contains_scout_and_weather() -> None:
    assert "scout" in broker.DEFAULT_PROVIDER_WEIGHTS
    assert "listenbrainz_weather" in broker.DEFAULT_PROVIDER_WEIGHTS


def test_default_provider_weights_sum_to_one() -> None:
    total = sum(broker.DEFAULT_PROVIDER_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# _recommend_from_scout
# ---------------------------------------------------------------------------

def _make_seed() -> dict[str, Any]:
    return {
        "track_id": "seed-1",
        "artist": "Test Artist",
        "title": "Test Title",
        "genre": "rock",
        "filepath": "C:/Music/test.flac",
        "file_exists": True,
    }


def test_recommend_from_scout_no_seed_returns_failed() -> None:
    result = broker._recommend_from_scout(
        seed_track=None, mode="flow", limit=6, novelty_band="stretch", weight=0.1,
    )
    assert result.status == ProviderStatus.FAILED
    assert result.provider == "scout"
    assert any(e.code == "no_seed" for e in result.errors)


def test_recommend_from_scout_scout_exception_returns_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Scout raises (e.g. no DISCOGS_API_TOKEN), status must be DEGRADED."""
    class _BrokenScout:
        def __init__(self) -> None:
            raise RuntimeError("DISCOGS_API_TOKEN not configured")

    monkeypatch.setattr("oracle.scout.Scout", _BrokenScout, raising=False)

    # Patch the lazy import inside the provider
    with patch.dict("sys.modules", {"oracle.scout": MagicMock(Scout=_BrokenScout)}):
        result = broker._recommend_from_scout(
            seed_track=_make_seed(), mode="flow", limit=6, novelty_band="stretch", weight=0.1,
        )
    assert result.status == ProviderStatus.DEGRADED
    assert result.provider == "scout"


def test_recommend_from_scout_empty_hits_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Scout returns no hits, status must be EMPTY."""
    mock_scout = MagicMock()
    mock_scout.cross_genre_hunt.return_value = []
    mock_scout_cls = MagicMock(return_value=mock_scout)

    with patch.dict("sys.modules", {"oracle.scout": MagicMock(Scout=mock_scout_cls)}):
        result = broker._recommend_from_scout(
            seed_track=_make_seed(), mode="flow", limit=6, novelty_band="stretch", weight=0.1,
        )
    assert result.status == ProviderStatus.EMPTY


def test_recommend_from_scout_ok_result_has_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Scout returns hits, status must be OK with acquisition-lead candidates."""
    hits = [
        {"artist": "Bridge Artist", "title": "Bridge Track", "acquisition_priority": 8.0},
    ]
    mock_scout = MagicMock()
    mock_scout.cross_genre_hunt.return_value = hits
    mock_scout_cls = MagicMock(return_value=mock_scout)

    monkeypatch.setattr(broker, "_load_track_by_artist_title", lambda a, t: None)

    with patch.dict("sys.modules", {"oracle.scout": MagicMock(Scout=mock_scout_cls)}):
        result = broker._recommend_from_scout(
            seed_track=_make_seed(), mode="flow", limit=6, novelty_band="stretch", weight=0.1,
        )
    assert result.status == ProviderStatus.OK
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.availability == Availability.ACQUISITION_LEAD
    assert c.evidence[0].type == "scout_cross_genre"
    assert c.evidence[0].source == "scout"


def test_recommend_from_scout_local_track_gets_local_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the hit already exists locally, evidence type should be scout_bridge_artist."""
    hits = [{"artist": "Local Artist", "title": "Local Track", "acquisition_priority": 5.0}]
    mock_scout = MagicMock()
    mock_scout.cross_genre_hunt.return_value = hits
    mock_scout_cls = MagicMock(return_value=mock_scout)

    existing = {
        "track_id": "local-1", "artist": "Local Artist", "title": "Local Track",
        "album": "Album", "filepath": "C:/Music/local.flac", "file_exists": True,
    }
    monkeypatch.setattr(broker, "_load_track_by_artist_title", lambda a, t: existing)

    with patch.dict("sys.modules", {"oracle.scout": MagicMock(Scout=mock_scout_cls)}):
        result = broker._recommend_from_scout(
            seed_track=_make_seed(), mode="flow", limit=6, novelty_band="stretch", weight=0.1,
        )
    assert result.status == ProviderStatus.OK
    c = result.candidates[0]
    assert c.availability == Availability.LOCAL
    assert c.evidence[0].type == "scout_bridge_artist"


# ---------------------------------------------------------------------------
# _recommend_from_listenbrainz_weather
# ---------------------------------------------------------------------------

def test_recommend_from_lb_weather_no_seed_returns_failed() -> None:
    result = broker._recommend_from_listenbrainz_weather(
        seed_track=None, limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.FAILED
    assert result.provider == "listenbrainz_weather"


def test_recommend_from_lb_weather_missing_artist_returns_failed() -> None:
    result = broker._recommend_from_listenbrainz_weather(
        seed_track={"track_id": "x", "artist": "", "title": "T"},
        limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.FAILED
    assert any(e.code == "no_artist" for e in result.errors)


def test_recommend_from_lb_weather_exception_returns_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        broker, "get_similar_artists_recordings",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("LB unavailable")),
    )
    result = broker._recommend_from_listenbrainz_weather(
        seed_track=_make_seed(), limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.DEGRADED


def test_recommend_from_lb_weather_empty_recordings_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(broker, "get_similar_artists_recordings", lambda *a, **kw: [])
    result = broker._recommend_from_listenbrainz_weather(
        seed_track=_make_seed(), limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.EMPTY


def test_recommend_from_lb_weather_ok_result_has_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recordings = [
        {
            "artist": "Similar Artist",
            "title": "Similar Track",
            "listen_count": 50000,
            "recording_mbid": "mbid-1",
            "similarity_score": 0.9,
            "source_artist": "Test Artist",
        },
    ]
    monkeypatch.setattr(broker, "get_similar_artists_recordings", lambda *a, **kw: recordings)
    monkeypatch.setattr(broker, "_load_track_by_artist_title", lambda a, t: None)

    result = broker._recommend_from_listenbrainz_weather(
        seed_track=_make_seed(), limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.OK
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.availability == Availability.ACQUISITION_LEAD
    assert c.evidence[0].type == "community_top_recording"
    assert c.novelty_band_fit == "stretch"


def test_recommend_from_lb_weather_local_track_gets_similar_artist_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recordings = [
        {
            "artist": "Local Similar", "title": "Found Track",
            "listen_count": 3000, "recording_mbid": "mbid-2",
            "similarity_score": 0.7, "source_artist": "Test Artist",
        },
    ]
    existing = {
        "track_id": "t-local", "artist": "Local Similar", "title": "Found Track",
        "album": "A", "filepath": "C:/Music/found.flac", "file_exists": True,
    }
    monkeypatch.setattr(broker, "get_similar_artists_recordings", lambda *a, **kw: recordings)
    monkeypatch.setattr(broker, "_load_track_by_artist_title", lambda a, t: existing)

    result = broker._recommend_from_listenbrainz_weather(
        seed_track=_make_seed(), limit=6, weight=0.1,
    )
    assert result.status == ProviderStatus.OK
    c = result.candidates[0]
    assert c.availability == Availability.LOCAL
    assert c.evidence[0].type == "community_similar_artist"


# ---------------------------------------------------------------------------
# get_similar_artists_recordings (unit — network mocked out)
# ---------------------------------------------------------------------------

def test_get_similar_artists_recordings_empty_artist_name() -> None:
    result = lb_module.get_similar_artists_recordings("")
    assert result == []


def test_get_similar_artists_recordings_no_mbid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If MBID resolution returns None the function should return []."""
    monkeypatch.setattr(lb_module, "_get_mbid", lambda name, sess: None)
    result = lb_module.get_similar_artists_recordings("Unknown Artist XYZ")
    assert result == []
