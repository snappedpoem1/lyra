from __future__ import annotations

from unittest import mock

from oracle.llm_config import diagnose_llm_config, load_llm_config, resolve_llm_config


def test_load_llm_config_normalizes_local(monkeypatch):
    monkeypatch.setenv("LYRA_LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("LYRA_LLM_BASE_URL", "")
    monkeypatch.setenv("LYRA_LLM_MODEL", "qwen2.5")

    config = load_llm_config()

    assert config.provider_type == "local"
    assert config.base_url == "http://127.0.0.1:1234/v1"
    assert config.supports_model_listing is True


def test_diagnose_uses_fallback_model(monkeypatch):
    monkeypatch.setenv("LYRA_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LYRA_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LYRA_LLM_MODEL", "missing-model")
    monkeypatch.setenv("LYRA_LLM_FALLBACK_MODEL", "available-model")

    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"id": "available-model"}]}

    with mock.patch("oracle.llm_config.requests.get", return_value=response):
        diagnostics = diagnose_llm_config()

    assert diagnostics["ok"] is True
    assert diagnostics["fallback_used"] is True
    assert diagnostics["selected_model"] == "available-model"


def test_diagnose_invalid_provider(monkeypatch):
    monkeypatch.setenv("LYRA_LLM_PROVIDER", "bad-provider")
    monkeypatch.setenv("LYRA_LLM_MODEL", "whatever")

    diagnostics = diagnose_llm_config()

    assert diagnostics["ok"] is False
    assert diagnostics["error_type"] == "provider_invalid"


def test_diagnose_anthropic_requires_model(monkeypatch):
    monkeypatch.setenv("LYRA_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LYRA_LLM_MODEL", raising=False)
    monkeypatch.delenv("LYRA_LLM_FALLBACK_MODEL", raising=False)

    diagnostics = diagnose_llm_config()

    assert diagnostics["ok"] is False
    assert diagnostics["error_type"] == "model_missing"


def test_resolve_llm_config_autodetects_private_host(monkeypatch):
    monkeypatch.setenv("LYRA_LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("LYRA_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LYRA_LLM_MODEL", "qwen2.5-14b-instruct")

    def fake_getaddrinfo(*args, **kwargs):
        return [
            (None, None, None, None, ("127.0.0.1", 0)),
            (None, None, None, None, ("10.2.0.2", 0)),
        ]

    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"id": "qwen2.5-14b-instruct"}]}

    def fake_requests_get(url, headers=None, timeout=None):
        if url == "http://10.2.0.2:1234/v1/models":
            return response
        raise OSError("connection refused")

    with mock.patch("oracle.llm_config.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with mock.patch("oracle.llm_config.requests.get", side_effect=fake_requests_get):
            resolved = resolve_llm_config(load_llm_config(resolve_endpoint=False))

    assert resolved.base_url == "http://10.2.0.2:1234/v1"
    assert resolved.base_url_source == "autodetect:10.2.0.2"
