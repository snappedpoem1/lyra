"""Normalized LLM provider configuration and diagnostics for Lyra."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


load_dotenv(override=False)


PROVIDER_ALIASES = {
    "lmstudio": "local",
    "local": "local",
    "openai": "openai",
    "openai_compatible": "openai_compatible",
    "openai-compatible": "openai_compatible",
    "anthropic": "anthropic",
    "none": "disabled",
    "disabled": "disabled",
    "off": "disabled",
}

OPENAI_COMPATIBLE_PROVIDERS = {"openai", "openai_compatible", "local"}


@dataclass(frozen=True)
class LyraLlmConfig:
    provider_type: str
    base_url: str
    model: str
    api_key: str
    api_key_env_var: str
    fallback_model: str
    timeout_seconds: int
    supports_model_listing: bool
    supports_chat_completions: bool
    supports_anthropic_messages: bool
    raw_provider: str

    def masked_summary(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "raw_provider": self.raw_provider,
            "base_url": self.base_url,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "timeout_seconds": self.timeout_seconds,
            "api_key_env_var": self.api_key_env_var,
            "api_key_present": bool(self.api_key),
            "supports_model_listing": self.supports_model_listing,
            "supports_chat_completions": self.supports_chat_completions,
            "supports_anthropic_messages": self.supports_anthropic_messages,
        }


def _parse_timeout(raw: str) -> int:
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def normalize_provider(value: str) -> str:
    normalized = PROVIDER_ALIASES.get((value or "").strip().lower())
    return normalized or "invalid"


def load_llm_config() -> LyraLlmConfig:
    raw_provider = os.environ.get("LYRA_LLM_PROVIDER", "local").strip() or "local"
    provider_type = normalize_provider(raw_provider)
    timeout_seconds = _parse_timeout(os.environ.get("LYRA_LLM_TIMEOUT_SECONDS", "30"))
    base_url = os.environ.get("LYRA_LLM_BASE_URL", "").strip()
    fallback_model = os.environ.get("LYRA_LLM_FALLBACK_MODEL", "").strip()
    model = os.environ.get("LYRA_LLM_MODEL", "").strip()
    api_key = os.environ.get("LYRA_LLM_API_KEY", "").strip()
    api_key_env_var = "LYRA_LLM_API_KEY"

    if provider_type in {"local", "openai_compatible"} and not base_url:
        base_url = "http://localhost:1234/v1"
    elif provider_type == "openai" and not base_url:
        base_url = "https://api.openai.com/v1"
        api_key_env_var = "LYRA_LLM_API_KEY"
    elif provider_type == "anthropic" and not base_url:
        base_url = "https://api.anthropic.com/v1"
        api_key_env_var = "LYRA_LLM_API_KEY"

    supports_model_listing = provider_type in OPENAI_COMPATIBLE_PROVIDERS
    supports_chat_completions = provider_type in OPENAI_COMPATIBLE_PROVIDERS
    supports_anthropic_messages = provider_type == "anthropic"

    return LyraLlmConfig(
        provider_type=provider_type,
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        fallback_model=fallback_model,
        timeout_seconds=timeout_seconds,
        supports_model_listing=supports_model_listing,
        supports_chat_completions=supports_chat_completions,
        supports_anthropic_messages=supports_anthropic_messages,
        raw_provider=raw_provider,
    )


def diagnose_llm_config(config: Optional[LyraLlmConfig] = None) -> Dict[str, Any]:
    config = config or load_llm_config()
    diagnostics: Dict[str, Any] = {
        "ok": False,
        "config": config.masked_summary(),
        "error_type": "",
        "error": "",
        "actions": [],
        "models": [],
        "selected_model": config.model,
        "fallback_used": False,
        "supports_model_probe": config.supports_model_listing,
    }

    if config.provider_type == "disabled":
        diagnostics["ok"] = True
        diagnostics["actions"] = ["AI-dependent features are disabled by configuration."]
        return diagnostics

    if config.provider_type == "invalid":
        diagnostics["error_type"] = "provider_invalid"
        diagnostics["error"] = f"Unsupported provider '{config.raw_provider}'."
        diagnostics["actions"] = [
            "Set LYRA_LLM_PROVIDER to one of: openai, anthropic, openai_compatible, local, disabled."
        ]
        return diagnostics

    if config.supports_anthropic_messages and not config.base_url.endswith("/v1"):
        diagnostics["error_type"] = "provider_endpoint_mismatch"
        diagnostics["error"] = "Anthropic provider must target an Anthropic-compatible /v1 base URL."
        diagnostics["actions"] = [
            "Set LYRA_LLM_BASE_URL to the Anthropic-compatible API root.",
            "Or switch LYRA_LLM_PROVIDER to openai_compatible/local if the endpoint exposes /v1/models.",
        ]
        return diagnostics

    if not config.model and not config.fallback_model:
        diagnostics["error_type"] = "model_missing"
        diagnostics["error"] = "No primary or fallback model is configured."
        diagnostics["actions"] = [
            "Set LYRA_LLM_MODEL.",
            "Optionally set LYRA_LLM_FALLBACK_MODEL for automatic recovery.",
        ]
        return diagnostics

    selected_model = config.model or config.fallback_model
    diagnostics["selected_model"] = selected_model

    if config.supports_model_listing:
        models_url = f"{config.base_url}/models"
        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        try:
            response = requests.get(models_url, headers=headers, timeout=config.timeout_seconds)
            if response.status_code != 200:
                diagnostics["error_type"] = "endpoint_probe_failed"
                diagnostics["error"] = f"Model probe failed with HTTP {response.status_code} from {models_url}."
                diagnostics["actions"] = [
                    "Check LYRA_LLM_BASE_URL and provider type.",
                    "If this is an Anthropic-style endpoint, switch LYRA_LLM_PROVIDER=anthropic.",
                ]
                return diagnostics
            payload = response.json()
            models = [item.get("id") for item in payload.get("data", []) if item.get("id")]
            diagnostics["models"] = models
            if config.model and config.model in models:
                diagnostics["ok"] = True
                return diagnostics
            if config.fallback_model and config.fallback_model in models:
                diagnostics["ok"] = True
                diagnostics["selected_model"] = config.fallback_model
                diagnostics["fallback_used"] = True
                diagnostics["actions"] = [
                    f"Primary model '{config.model}' is unavailable; fallback '{config.fallback_model}' will be used."
                ]
                return diagnostics
            diagnostics["error_type"] = "model_not_available"
            diagnostics["error"] = f"Configured model '{selected_model}' is not present in {models_url}."
            diagnostics["actions"] = [
                "Call /v1/models on the configured endpoint and choose a listed model.",
                "Or switch LYRA_LLM_PROVIDER to the correct provider family for that endpoint.",
                "Or set LYRA_LLM_PROVIDER=disabled to disable AI-dependent features cleanly.",
            ]
            return diagnostics
        except requests.RequestException as exc:
            diagnostics["error_type"] = "endpoint_probe_failed"
            diagnostics["error"] = f"Model probe failed: {exc}"
            diagnostics["actions"] = [
                "Verify the base URL is reachable.",
                "If this endpoint is Anthropic-compatible, set LYRA_LLM_PROVIDER=anthropic.",
            ]
            return diagnostics

    # Anthropic path: validate only provider family and non-empty model.
    diagnostics["ok"] = True
    if config.model.lower().startswith("qwen"):
        diagnostics["actions"] = [
            "Configured Anthropic provider with a qwen model. Verify the endpoint actually supports that model before enabling agent features."
        ]
    return diagnostics


def main(argv: Optional[List[str]] = None) -> int:
    diagnostics = diagnose_llm_config()
    print(json.dumps(diagnostics, indent=2))
    return 0 if diagnostics.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
