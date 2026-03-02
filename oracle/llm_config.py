"""Normalized LLM provider configuration and diagnostics for Lyra."""

from __future__ import annotations

from dataclasses import dataclass, replace
import ipaddress
import json
import os
import socket
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

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
MAX_LOCAL_DISCOVERY_CANDIDATES = 4
MAX_MODEL_PROBE_TIMEOUT_SECONDS = 2


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
    base_url_source: str = "configured"

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
            "base_url_source": self.base_url_source,
        }


def _parse_timeout(raw: str) -> int:
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def normalize_provider(value: str) -> str:
    normalized = PROVIDER_ALIASES.get((value or "").strip().lower())
    return normalized or "invalid"


def _normalize_openai_base_url(base_url: str, *, default_host: str = "127.0.0.1", default_port: int = 1234) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return f"http://{default_host}:{default_port}/v1"
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    scheme = parsed.scheme or "http"
    host = parsed.hostname or default_host
    if host == "localhost":
        host = "127.0.0.1"
    port = parsed.port or default_port
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    elif not path.endswith("/v1"):
        path = f"{path}/v1"
    return f"{scheme}://{host}:{port}{path}"


def _probe_models(base_url: str, api_key: str, timeout_seconds: int) -> Tuple[bool, List[str], str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    models_url = f"{base_url.rstrip('/')}/models"
    try:
        response = requests.get(
            models_url,
            headers=headers,
            timeout=max(1, min(timeout_seconds, MAX_MODEL_PROBE_TIMEOUT_SECONDS)),
        )
        if response.status_code != 200:
            return False, [], f"HTTP {response.status_code} from {models_url}"
        payload = response.json()
        models = [item.get("id") for item in payload.get("data", []) if item.get("id")]
        return True, models, ""
    except Exception as exc:
        return False, [], str(exc)


def _iter_local_hosts() -> Iterable[str]:
    seen: set[str] = set()
    configured = [item.strip() for item in os.environ.get("LYRA_LLM_DISCOVERY_HOSTS", "").split(",") if item.strip()]
    for host in [*configured, "127.0.0.1", "localhost"]:
        if host not in seen:
            seen.add(host)
            yield host

    names = [socket.gethostname(), socket.getfqdn()]
    for name in names:
        if not name:
            continue
        try:
            infos = socket.getaddrinfo(name, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        except OSError:
            continue
        for info in infos:
            host = info[4][0]
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_private:
                normalized = str(ip)
                if normalized not in seen:
                    seen.add(normalized)
                    yield normalized


def resolve_local_base_url(base_url: str, api_key: str = "", timeout_seconds: int = 30) -> Tuple[str, str]:
    normalized = _normalize_openai_base_url(base_url)
    parsed = urlparse(normalized)
    scheme = parsed.scheme or "http"
    port = parsed.port or 1234
    path = parsed.path.rstrip("/") or "/v1"

    candidates: list[tuple[str, str]] = [(normalized, "configured")]
    for host in _iter_local_hosts():
        candidate = f"{scheme}://{host}:{port}{path}"
        if candidate != normalized:
            candidates.append((candidate, f"autodetect:{host}"))

    for candidate, source in candidates[:MAX_LOCAL_DISCOVERY_CANDIDATES]:
        ok, _, _ = _probe_models(candidate, api_key, timeout_seconds)
        if ok:
            return candidate, source
    return normalized, "configured"


def load_llm_config(resolve_endpoint: bool = False) -> LyraLlmConfig:
    raw_provider = os.environ.get("LYRA_LLM_PROVIDER", "local").strip() or "local"
    provider_type = normalize_provider(raw_provider)
    timeout_seconds = _parse_timeout(os.environ.get("LYRA_LLM_TIMEOUT_SECONDS", "30"))
    base_url = os.environ.get("LYRA_LLM_BASE_URL", "").strip()
    fallback_model = os.environ.get("LYRA_LLM_FALLBACK_MODEL", "").strip()
    model = os.environ.get("LYRA_LLM_MODEL", "").strip()
    api_key = os.environ.get("LYRA_LLM_API_KEY", "").strip()
    api_key_env_var = "LYRA_LLM_API_KEY"

    if provider_type in {"local", "openai_compatible"} and not base_url:
        base_url = "http://127.0.0.1:1234/v1"
    elif provider_type == "openai" and not base_url:
        base_url = "https://api.openai.com/v1"
        api_key_env_var = "LYRA_LLM_API_KEY"
    elif provider_type == "anthropic" and not base_url:
        base_url = "https://api.anthropic.com/v1"
        api_key_env_var = "LYRA_LLM_API_KEY"

    supports_model_listing = provider_type in OPENAI_COMPATIBLE_PROVIDERS
    supports_chat_completions = provider_type in OPENAI_COMPATIBLE_PROVIDERS
    supports_anthropic_messages = provider_type == "anthropic"

    base_url_source = "configured"
    normalized_base_url = base_url.rstrip("/")
    if provider_type == "local":
        normalized_base_url = _normalize_openai_base_url(normalized_base_url)
        if resolve_endpoint:
            normalized_base_url, base_url_source = resolve_local_base_url(
                normalized_base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )

    return LyraLlmConfig(
        provider_type=provider_type,
        base_url=normalized_base_url,
        model=model,
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        fallback_model=fallback_model,
        timeout_seconds=timeout_seconds,
        supports_model_listing=supports_model_listing,
        supports_chat_completions=supports_chat_completions,
        supports_anthropic_messages=supports_anthropic_messages,
        raw_provider=raw_provider,
        base_url_source=base_url_source,
    )


def resolve_llm_config(config: Optional[LyraLlmConfig] = None) -> LyraLlmConfig:
    current = config or load_llm_config(resolve_endpoint=False)
    if current.provider_type != "local":
        return current
    resolved_base_url, source = resolve_local_base_url(
        current.base_url,
        api_key=current.api_key,
        timeout_seconds=current.timeout_seconds,
    )
    return replace(current, base_url=resolved_base_url, base_url_source=source)


def diagnose_llm_config(
    config: Optional[LyraLlmConfig] = None,
    *,
    resolve_endpoint: bool = True,
) -> Dict[str, Any]:
    config = config or load_llm_config(resolve_endpoint=False)
    if resolve_endpoint:
        config = resolve_llm_config(config)
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
            response = requests.get(
                models_url,
                headers=headers,
                timeout=max(1, min(config.timeout_seconds, MAX_MODEL_PROBE_TIMEOUT_SECONDS)),
            )
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
