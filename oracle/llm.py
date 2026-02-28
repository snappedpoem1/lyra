"""Provider-aware LLM client adapter for Lyra Oracle."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

import requests

from oracle.config import get_llm_settings
from oracle.llm_config import OPENAI_COMPATIBLE_PROVIDERS, diagnose_llm_config, load_llm_config, resolve_llm_config

logger = logging.getLogger(__name__)
_STATUS_CACHE: Dict[str, Any] = {}
_STATUS_CACHE_TS: float = 0.0
_STATUS_CACHE_TTL_SECONDS = 15.0


@dataclass
class LLMStatus:
    ok: bool
    provider: str
    model: str
    base_url: str
    error: str = ""
    error_type: str = ""
    actions: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.error:
            payload["error"] = self.error
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.actions:
            payload["actions"] = list(self.actions)
        return payload


@dataclass
class LLMClient:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    fallback_model: str = ""
    supports_model_listing: bool = False
    supports_chat_completions: bool = False
    supports_anthropic_messages: bool = False
    _cached_models: List[str] = field(default_factory=list)
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "LLMClient":
        config = resolve_llm_config(load_llm_config(resolve_endpoint=False))
        return cls(
            provider=config.provider_type,
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
            fallback_model=config.fallback_model,
            supports_model_listing=config.supports_model_listing,
            supports_chat_completions=config.supports_chat_completions,
            supports_anthropic_messages=config.supports_anthropic_messages,
        )

    def _diagnose(self) -> Dict[str, Any]:
        return diagnose_llm_config()

    def _available(self) -> bool:
        return self.provider != "disabled"

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url.rstrip("/"),
                api_key=self.api_key or "lyra-local",
                timeout=float(self.timeout_seconds),
                max_retries=1,
            )
        return self._client

    def _fetch_models(self) -> List[str]:
        if not self.supports_model_listing:
            return []
        try:
            client = self._get_client()
            response = client.models.list()
            models = [m.id for m in response.data if getattr(m, "id", None)]
            self._cached_models = models
            return models
        except Exception as exc:
            logger.warning("[LLM] model list failed: %s", exc)
            return []

    def _resolve_model(self) -> tuple[str, Optional[Dict[str, Any]]]:
        diagnostics = self._diagnose()
        if diagnostics.get("ok"):
            selected = diagnostics.get("selected_model") or self.model or self.fallback_model
            if diagnostics.get("fallback_used") and selected:
                self.model = selected
            return selected, None
        return "", diagnostics

    def check_available(self, probe: bool = False) -> LLMStatus:
        diagnostics = self._diagnose()
        if not diagnostics.get("ok"):
            return LLMStatus(
                ok=False,
                provider=self.provider,
                model=diagnostics.get("selected_model") or self.model,
                base_url=self.base_url,
                error=diagnostics.get("error", "LLM unavailable"),
                error_type=diagnostics.get("error_type", ""),
                actions=diagnostics.get("actions", []),
            )

        model = diagnostics.get("selected_model") or self.model or self.fallback_model
        if probe:
            probe_result = self.chat(
                [{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_tokens=1,
                timeout=2.0,
            )
            if not probe_result.get("ok"):
                return LLMStatus(
                    ok=False,
                    provider=self.provider,
                    model=model,
                    base_url=self.base_url,
                    error=probe_result.get("error", "chat probe failed"),
                    error_type=probe_result.get("error_type", ""),
                    actions=probe_result.get("actions", []),
                )

        return LLMStatus(ok=True, provider=self.provider, model=model, base_url=self.base_url)

    def _chat_openai_compatible(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        json_schema: Optional[Dict[str, Any]],
        timeout: Optional[float],
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if timeout:
            kwargs["timeout"] = timeout

        is_json = False
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("name", "response"),
                    "strict": True,
                    "schema": json_schema.get("schema", {}),
                },
            }
            is_json = True
        elif json_mode:
            kwargs["response_format"] = {"type": "json_object"}
            is_json = True

        response = self._get_client().chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        if is_json:
            try:
                data = json.loads(content)
                return {"ok": True, "data": data, "text": content, "model": model, "provider": self.provider}
            except json.JSONDecodeError as exc:
                return {"ok": False, "error": f"JSON parse: {exc}", "text": content}
        return {"ok": True, "text": content, "model": model, "provider": self.provider}

    def _chat_anthropic(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout: Optional[float],
    ) -> Dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = requests.post(
            f"{self.base_url.rstrip('/')}/messages",
            headers=headers,
            json=payload,
            timeout=timeout or self.timeout_seconds,
        )
        if response.status_code >= 400:
            return {
                "ok": False,
                "error": f"HTTP {response.status_code}: {response.text[:240]}",
                "error_type": "anthropic_messages_error",
            }
        payload = response.json()
        content_blocks = payload.get("content") or []
        text = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
        return {"ok": True, "text": text, "model": model, "provider": self.provider}

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        system: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self._available():
            return {"ok": False, "error": "LLM not configured", "text": "", "error_type": "provider_disabled"}

        model, diagnostics = self._resolve_model()
        if diagnostics:
            return {
                "ok": False,
                "error": diagnostics.get("error", "LLM unavailable"),
                "text": "",
                "error_type": diagnostics.get("error_type", ""),
                "actions": diagnostics.get("actions", []),
            }

        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            if self.provider in OPENAI_COMPATIBLE_PROVIDERS:
                return self._chat_openai_compatible(
                    model=model,
                    messages=all_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    json_schema=json_schema,
                    timeout=timeout,
                )
            if self.provider == "anthropic":
                if json_mode or json_schema:
                    return {
                        "ok": False,
                        "error": "Anthropic path does not support structured JSON mode in this adapter yet.",
                        "text": "",
                        "error_type": "unsupported_feature",
                    }
                return self._chat_anthropic(
                    model=model,
                    messages=all_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            return {"ok": False, "error": f"Unsupported provider: {self.provider}", "text": "", "error_type": "provider_invalid"}
        except Exception as exc:
            err = str(exc)
            logger.warning("[LLM] Error: %s", err)
            return {"ok": False, "error": err, "text": "", "error_type": "request_failed"}

    def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system: Optional[str] = None,
    ) -> Generator[str, None, None]:
        if self.provider not in OPENAI_COMPATIBLE_PROVIDERS:
            result = self.chat(messages, temperature=temperature, max_tokens=max_tokens, system=system)
            if result.get("ok") and result.get("text"):
                yield result["text"]
            return

        model, diagnostics = self._resolve_model()
        if diagnostics or not model:
            return

        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            with self._get_client().chat.completions.stream(
                model=model,
                messages=all_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as exc:
            logger.warning("[LLM] Stream error: %s", exc)

    def classify(
        self,
        artist: str,
        title: str,
        categories: List[str],
        context: str = "",
    ) -> Dict[str, Any]:
        cats_str = ", ".join(f'"{c}"' for c in categories)
        prompt = (
            f"Artist: {artist}\nTitle: {title}\n"
            + (f"Context: {context}\n" if context else "")
            + f"\nClassify into one of: [{cats_str}]"
        )
        result = self.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
            json_schema={
                "name": "track_classification",
                "schema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": categories},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "reason": {"type": "string"},
                    },
                    "required": ["category", "confidence", "reason"],
                    "additionalProperties": False,
                },
            },
            system=(
                "You are a music metadata expert and library curator. "
                "Identify karaoke tracks, tribute bands, mislabeled rips, and low-quality content. "
                "Respond with JSON only."
            ),
        )
        if not result.get("ok") or "data" not in result:
            return {"ok": False, "category": None, "confidence": 0.0, "reason": result.get("error", "unknown")}
        data = result["data"]
        return {
            "ok": True,
            "category": data.get("category"),
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason", ""),
        }

    def narrate_playlist(self, tracks: List[Dict[str, str]], arc_type: str = "journey") -> str:
        track_list = "\n".join(
            f"{i+1}. {t.get('artist', '?')} - {t.get('title', '?')}"
            for i, t in enumerate(tracks[:20])
        )
        prompt = f"Arc: {arc_type}\n\n{track_list}\n\nDescribe this journey in 2-3 sentences."
        chunks = list(
            self.stream(
                [{"role": "user", "content": prompt}],
                temperature=0.75,
                max_tokens=150,
                system=(
                    "You are Lyra, a poetic music intelligence. "
                    "Describe playlists with evocative, sensory language. Be concise."
                ),
            )
        )
        return "".join(chunks)

    def list_models(self) -> List[str]:
        return self._fetch_models()


def get_llm_status(force_refresh: bool = False) -> Dict[str, Any]:
    global _STATUS_CACHE, _STATUS_CACHE_TS
    now = time.time()
    if not force_refresh and _STATUS_CACHE and (now - _STATUS_CACHE_TS) < _STATUS_CACHE_TTL_SECONDS:
        return dict(_STATUS_CACHE)

    client = LLMClient.from_env()
    settings = get_llm_settings()
    status = client.check_available(probe=False)
    payload = status.as_dict()
    payload["status"] = "ok" if status.ok else "unavailable"
    payload["fallback_model"] = settings.get("fallback_model", "")
    payload["supports_model_listing"] = settings.get("supports_model_listing", False)
    _STATUS_CACHE = dict(payload)
    _STATUS_CACHE_TS = now
    return payload
