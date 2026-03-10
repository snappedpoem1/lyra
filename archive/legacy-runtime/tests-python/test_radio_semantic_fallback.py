from __future__ import annotations

import sys
import types

from oracle.radio import Radio


def test_semantic_similar_tracks_handles_missing_seed_embedding(monkeypatch):
    class FakeCollection:
        def get(self, ids=None, include=None):
            return {"embeddings": []}

    class FakeClient:
        def get_or_create_collection(self, _name):
            return FakeCollection()

    fake_chromadb = types.SimpleNamespace(PersistentClient=lambda path=None: FakeClient())
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    radio = Radio()
    monkeypatch.setattr(
        radio,
        "_random_tracks",
        lambda count: [{"track_id": "fallback", "metadata": {"artist": "A", "title": "T"}}],
    )

    result = radio._semantic_similar_tracks("missing-track", 1)
    assert result[0]["track_id"] == "fallback"
