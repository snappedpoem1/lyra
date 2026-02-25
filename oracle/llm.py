"""LLM client adapter for Lyra Oracle.

Uses the OpenAI SDK pointed at LM Studio's OpenAI-compatible server
(default: http://localhost:1234/v1).

Features:
- JSON Schema structured output (grammar-constrained, guaranteed valid JSON)
- Streaming via generator
- Tool/function calling
- Auto-detect loaded model when none is configured
- Graceful no-op when LM Studio is offline or provider='none'
"""

from __future__ import annotations

import json
import logging
<<<<<<< HEAD
=======
import time
>>>>>>> fc77b41 (Update workspace state and diagnostics)
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from oracle.config import get_llm_settings

logger = logging.getLogger(__name__)
<<<<<<< HEAD
=======
_STATUS_CACHE: Dict[str, Any] = {}
_STATUS_CACHE_TS: float = 0.0
_STATUS_CACHE_TTL_SECONDS = 15.0
>>>>>>> fc77b41 (Update workspace state and diagnostics)


@dataclass
class LLMStatus:
    ok: bool
    provider: str
    model: str
    base_url: str
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass
class LLMClient:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    _cached_models: List[str] = field(default_factory=list)
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "LLMClient":
        settings = get_llm_settings()
        return cls(
            provider=settings["provider"],
            base_url=settings["base_url"],
            model=settings["model"],
            api_key=settings["api_key"],
            timeout_seconds=settings["timeout_seconds"],
        )

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _get_client(self):
        """Lazy-init the OpenAI SDK client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url.rstrip("/"),
                api_key=self.api_key or "lm-studio",  # LM Studio ignores the key
                timeout=float(self.timeout_seconds),
                max_retries=1,
            )
        return self._client

    def _available(self) -> bool:
        return self.provider != "none"

    def _resolve_model(self) -> str:
        """Return configured model, or auto-detect first loaded model."""
        if self.model:
            return self.model
        models = self._fetch_models()
        if models:
            logger.info(f"[LLM] Auto-detected model: {models[0]}")
            self.model = models[0]
        return self.model

    def _fetch_models(self) -> List[str]:
        if not self._available():
            return []
        try:
            client = self._get_client()
            response = client.models.list()
            models = [m.id for m in response.data if m.id]
            self._cached_models = models
            return models
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

<<<<<<< HEAD
    def check_available(self) -> LLMStatus:
        if not self._available():
            return LLMStatus(ok=False, provider=self.provider, model=self.model,
                             base_url=self.base_url, error="provider=none")
        model = self._resolve_model()
        if not model:
            return LLMStatus(ok=False, provider=self.provider, model="",
                             base_url=self.base_url, error="no model loaded in LM Studio")
        probe = self.chat([{"role": "user", "content": "ping"}],
                          temperature=0.0, max_tokens=1, timeout=2.0)
        if probe.get("ok"):
            return LLMStatus(ok=True, provider=self.provider, model=model,
                             base_url=self.base_url)
        return LLMStatus(ok=False, provider=self.provider, model=model,
                         base_url=self.base_url, error=probe.get("error", "chat probe failed"))
=======
    def check_available(self, probe: bool = False) -> LLMStatus:
        if not self._available():
            return LLMStatus(ok=False, provider=self.provider, model=self.model,
                             base_url=self.base_url, error="provider=none")

        models = self._fetch_models()
        if self.model:
            model = self.model
            if not models:
                return LLMStatus(
                    ok=False,
                    provider=self.provider,
                    model=model,
                    base_url=self.base_url,
                    error="model list unavailable or no model loaded",
                )
            if model not in models:
                return LLMStatus(
                    ok=False,
                    provider=self.provider,
                    model=model,
                    base_url=self.base_url,
                    error=f"configured model not loaded: {model}",
                )
        else:
            if not models:
                return LLMStatus(
                    ok=False,
                    provider=self.provider,
                    model="",
                    base_url=self.base_url,
                    error="no model loaded in local LLM server",
                )
            model = models[0]
            self.model = model

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
                )

        return LLMStatus(ok=True, provider=self.provider, model=model, base_url=self.base_url)
>>>>>>> fc77b41 (Update workspace state and diagnostics)

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
        """Send a chat completion request.

        Args:
            messages: List of role/content dicts.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.
            json_mode: Simple JSON object mode (any valid JSON).
            json_schema: Full JSON Schema dict for grammar-constrained output.
                         Overrides json_mode when provided.
            system: Optional system prompt prepended to messages.
            timeout: Optional override for the HTTP timeout.

        Returns:
            Dict with 'ok', 'text', and optionally 'data' (parsed JSON).
        """
        if not self._available():
            return {"ok": False, "error": "LLM not configured", "text": ""}

        model = self._resolve_model()
        if not model:
            return {"ok": False, "error": "no model loaded in LM Studio", "text": ""}

        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": all_messages,
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

        try:
            client = self._get_client()
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            if is_json:
                try:
                    data = json.loads(content)
                    return {"ok": True, "data": data, "text": content,
                            "model": model, "provider": self.provider}
                except json.JSONDecodeError as exc:
                    logger.warning(f"[LLM] JSON parse failed: {exc}; raw={content[:200]}")
                    return {"ok": False, "error": f"JSON parse: {exc}", "text": content}

            return {"ok": True, "text": content, "model": model, "provider": self.provider}

        except Exception as exc:
            err = str(exc)
            if "connection" in err.lower() or "refused" in err.lower():
                logger.debug(f"[LLM] LM Studio offline: {exc}")
            else:
                logger.warning(f"[LLM] Error: {exc}")
            return {"ok": False, "error": err, "text": ""}

    def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream a chat completion, yielding text chunks as they arrive."""
        if not self._available():
            return

        model = self._resolve_model()
        if not model:
            return

        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            client = self._get_client()
            with client.chat.completions.stream(
                model=model,
                messages=all_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as exc:
            logger.warning(f"[LLM] Stream error: {exc}")

    def classify(
        self,
        artist: str,
        title: str,
        categories: List[str],
        context: str = "",
    ) -> Dict[str, Any]:
        """Classify a track into one of the given categories using JSON Schema mode.

        Uses grammar-constrained output — result is guaranteed to be valid JSON
        matching the schema. qwen2.5-14b-instruct at temperature=0.0 is reliable
        for this task.

        Args:
            artist: Track artist.
            title: Track title.
            categories: List of allowed category strings.
            context: Optional additional context (album, filename, bitrate).

        Returns:
            Dict with 'category', 'confidence' (0-1), 'reason', 'ok'.
        """
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
            return {"ok": False, "category": None, "confidence": 0.0,
                    "reason": result.get("error", "unknown")}
        data = result["data"]
        return {
            "ok": True,
            "category": data.get("category"),
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason", ""),
        }

    def narrate_playlist(
        self,
        tracks: List[Dict[str, str]],
        arc_type: str = "journey",
    ) -> str:
        """Generate a short poetic description of a playlist's emotional arc.

        Args:
            tracks: List of dicts with 'artist' and 'title' keys.
            arc_type: Description of the intended arc (e.g. 'late night descent').

        Returns:
            Prose narrative string (streamed, returned as complete string).
        """
        track_list = "\n".join(
            f"{i+1}. {t.get('artist','?')} - {t.get('title','?')}"
            for i, t in enumerate(tracks[:20])
        )
        prompt = f"Arc: {arc_type}\n\n{track_list}\n\nDescribe this journey in 2-3 sentences."
        chunks = list(self.stream(
            [{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=150,
            system=(
                "You are Lyra, a poetic music intelligence. "
                "Describe playlists with evocative, sensory language. Be concise."
            ),
        ))
        return "".join(chunks)

    def list_models(self) -> List[str]:
        return self._fetch_models()


<<<<<<< HEAD
def get_llm_status() -> Dict[str, Any]:
    client = LLMClient.from_env()
    status = client.check_available()
    payload = status.as_dict()
    payload["status"] = "ok" if status.ok else "unavailable"
=======
def get_llm_status(force_refresh: bool = False) -> Dict[str, Any]:
    global _STATUS_CACHE, _STATUS_CACHE_TS
    now = time.time()
    if (
        not force_refresh
        and _STATUS_CACHE
        and (now - _STATUS_CACHE_TS) < _STATUS_CACHE_TTL_SECONDS
    ):
        return dict(_STATUS_CACHE)

    client = LLMClient.from_env()
    status = client.check_available(probe=False)
    payload = status.as_dict()
    payload["status"] = "ok" if status.ok else "unavailable"
    _STATUS_CACHE = dict(payload)
    _STATUS_CACHE_TS = now
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    return payload
