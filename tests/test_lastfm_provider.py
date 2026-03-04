from __future__ import annotations

import types

import oracle.enrichers.lastfm as lf


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise lf.requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_request_retries_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429)
        return _Resp(200, payload={"track": {"name": "ok"}})

    monkeypatch.setattr(lf, "_SESSION", types.SimpleNamespace(get=fake_get))
    monkeypatch.setattr(lf.time, "sleep", lambda _s: None)
    monkeypatch.setattr(lf.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(lf, "_MAX_RETRIES", 3)
    monkeypatch.setattr(lf, "_LAST_REQUEST_TS", 0.0)
    monkeypatch.setattr(lf, "_api_key", lambda: "test-key")

    result = lf._request("track.getInfo", {"artist": "A", "track": "B"})
    assert result == {"track": {"name": "ok"}}
    assert calls["n"] == 2


def test_build_track_profile_extracts_tags(monkeypatch):
    monkeypatch.setattr(
        lf,
        "track_get_info",
        lambda artist, title: {
            "track": {
                "listeners": "123",
                "playcount": "456",
                "duration": "200000",
                "url": "https://last.fm/track",
                "toptags": {"tag": [{"name": "trip hop"}, {"name": "electronic"}]},
            }
        },
    )
    monkeypatch.setattr(lf, "track_get_top_tags", lambda artist, title: {})
    monkeypatch.setattr(lf, "artist_get_top_tags", lambda artist: {})
    monkeypatch.setattr(lf, "track_get_similar", lambda artist, title, limit=10: {"similartracks": {"track": []}})
    monkeypatch.setattr(lf, "artist_get_similar", lambda artist, limit=10: {"similarartists": {"artist": []}})

    profile = lf.build_track_profile("Massive Attack", "Teardrop")
    assert profile["provider"] == "lastfm"
    assert profile["tags"] == ["trip hop", "electronic"]
    assert profile["listeners"] == "123"
