from __future__ import annotations

import oracle.search as search_module


def test_search_falls_back_when_semantic_stack_unavailable(monkeypatch):
    class FakeCursor:
        def execute(self, _query, _params=()):
            return self

        def fetchall(self):
            return [
                ("track-1", "Artist A", "Song A", "Album A", "2020", "C:/music/song-a.flac"),
            ]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(search_module, "LyraChromaStore", None)
    monkeypatch.setattr(search_module, "get_connection", lambda timeout=10.0: FakeConn())

    results = search_module.search("song a", n=5)

    assert len(results) == 1
    assert results[0]["track_id"] == "track-1"
    assert results[0]["fallback_reason"] == "chromadb unavailable"
    assert "score" in results[0]


def test_fallback_text_search_ranks_partial_phrase_matches(monkeypatch):
    rows = [
        ("track-1", "Midnight Drive", "Neon Night", "City Lights", "2020", "C:/music/track-1.flac"),
        ("track-2", "Drivealone", "Sunrise", "Morning Run", "2021", "C:/music/track-2.flac"),
        ("track-3", "Ambient Artist", "Static", "Daylight", "2019", "C:/music/track-3.flac"),
    ]

    class FakeCursor:
        def execute(self, _query, _params=()):
            return self

        def fetchall(self):
            return rows

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(search_module, "get_connection", lambda timeout=10.0: FakeConn())

    results = search_module.fallback_text_search("late night drive", n=2, reason="debug")

    assert len(results) == 2
    assert results[0]["track_id"] == "track-1"
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["fallback_mode"] == "metadata"
