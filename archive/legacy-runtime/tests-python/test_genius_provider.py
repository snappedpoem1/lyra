from __future__ import annotations

import types

import oracle.enrichers.genius as gn


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise gn.requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_request_retries_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers, params, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429)
        return _Resp(200, payload={"response": {"ok": True}})

    monkeypatch.setattr(gn, "_SESSION", types.SimpleNamespace(get=fake_get))
    monkeypatch.setattr(gn.time, "sleep", lambda _s: None)
    monkeypatch.setattr(gn, "_MAX_RETRIES", 3)
    monkeypatch.setattr(gn, "_token", lambda: "test-token")

    result = gn._request("/search", {"q": "test"})
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_build_song_profile_uses_best_hit(monkeypatch):
    monkeypatch.setattr(
        gn,
        "search",
        lambda q, per_page=10: [
            {"id": 1, "title": "Wrong Song", "primary_artist": {"name": "Wrong Artist"}},
            {"id": 2, "title": "Pink + White", "primary_artist": {"name": "Frank Ocean"}},
        ],
    )
    monkeypatch.setattr(
        gn,
        "get_song",
        lambda song_id, text_format="plain": {
            "id": song_id,
            "title": "Pink + White",
            "primary_artist": {"name": "Frank Ocean"},
            "url": "https://genius.com/x",
            "stats": {"pageviews": 999, "hot": False},
            "description": {"plain": "Test description"},
        },
    )

    profile = gn.build_song_profile("Frank Ocean", "Pink + White")
    assert profile["provider"] == "genius"
    assert profile["song_id"] == 2
    assert profile["artist"] == "Frank Ocean"
    assert profile["pageviews"] == 999
