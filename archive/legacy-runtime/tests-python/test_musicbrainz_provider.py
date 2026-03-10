from __future__ import annotations

import types

import oracle.enrichers.musicbrainz as mb


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise mb.requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_request_retries_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params, headers, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, headers={"Retry-After": "0"})
        return _Resp(200, payload={"ok": True})

    monkeypatch.setattr(mb, "_SESSION", types.SimpleNamespace(get=fake_get))
    monkeypatch.setattr(mb.time, "sleep", lambda _s: None)
    monkeypatch.setattr(mb.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(mb, "_MAX_RETRIES", 3)
    monkeypatch.setattr(mb, "_LAST_REQUEST_TS", 0.0)

    result = mb._request("https://musicbrainz.org/ws/2/recording", {"fmt": "json"})
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_request_returns_empty_after_retries(monkeypatch):
    def always_503(url, params, headers, timeout):
        return _Resp(503)

    monkeypatch.setattr(mb, "_SESSION", types.SimpleNamespace(get=always_503))
    monkeypatch.setattr(mb.time, "sleep", lambda _s: None)
    monkeypatch.setattr(mb.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(mb, "_MAX_RETRIES", 2)
    monkeypatch.setattr(mb, "_LAST_REQUEST_TS", 0.0)

    result = mb._request("https://musicbrainz.org/ws/2/recording", {"fmt": "json"})
    assert result == {}

