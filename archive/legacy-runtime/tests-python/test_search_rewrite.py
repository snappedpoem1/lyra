from __future__ import annotations

from dataclasses import dataclass

from oracle.api.blueprints import search as search_blueprint


@dataclass
class _FakeStatus:
    ok: bool = True

    def as_dict(self) -> dict:
        return {"ok": self.ok, "provider": "test", "model": "fake", "base_url": "http://fake"}


class _FakeLLMClient:
    @classmethod
    def from_env(cls):
        return cls()

    def check_available(self):
        return _FakeStatus(ok=True)

    def chat(self, *_args, **_kwargs):
        return {
            "ok": True,
            "data": {
                "clap_query": {"text": " cinematic bassline pressure "},
                "n": "7",
                "intent": {"label": "vibe-search"},
                "rationale": {"value": "normalized nested provider response"},
            },
        }


def test_search_rewrite_handles_nested_provider_payload(monkeypatch):
    monkeypatch.setattr(search_blueprint, "LLMClient", _FakeLLMClient)

    rewritten = search_blueprint._rewrite_search_query_with_llm("raw query", 5)
    assert rewritten["query"] == "cinematic bassline pressure"
    assert rewritten["n"] == 7
    assert rewritten["intent"] == "vibe-search"
    assert rewritten["rationale"] == "normalized nested provider response"
