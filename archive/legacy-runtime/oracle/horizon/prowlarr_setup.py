"""Prowlarr indexer setup helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
import os

import requests


def _prowlarr_base_url() -> str:
    return (os.getenv("PROWLARR_BASE_URL") or os.getenv("PROWLARR_URL") or "http://localhost:9696").rstrip("/")


def _prowlarr_api_key() -> str:
    key = (os.getenv("PROWLARR_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Missing PROWLARR_API_KEY")
    return key


def _request(method: str, path: str, *, json_data: Optional[Dict[str, Any]] = None) -> requests.Response:
    url = f"{_prowlarr_base_url()}{path}"
    headers = {"X-Api-Key": _prowlarr_api_key()}
    resp = requests.request(method, url, headers=headers, json=json_data, timeout=30)
    resp.raise_for_status()
    return resp


def _set_field(fields: List[Dict[str, Any]], name: str, value: Any) -> None:
    for field in fields:
        if field.get("name") == name:
            field["value"] = value
            return


def _find_rutracker_schema() -> Dict[str, Any]:
    schemas = _request("GET", "/api/v1/indexer/schema").json()
    for schema in schemas:
        if str(schema.get("implementation", "")).lower() == "rutracker":
            return schema
    raise RuntimeError("RuTracker schema not found in Prowlarr")


def _find_existing_rutracker() -> Optional[Dict[str, Any]]:
    indexers = _request("GET", "/api/v1/indexer").json()
    for indexer in indexers:
        impl = str(indexer.get("implementation", "")).lower()
        name = str(indexer.get("name", "")).lower()
        if impl == "rutracker" or "rutracker" in name:
            return indexer
    return None


def _test_indexer(payload: Dict[str, Any]) -> tuple[bool, str]:
    try:
        resp = _request("POST", "/api/v1/indexer/test", json_data=payload)
        message = ""
        try:
            body = resp.json()
            message = str(body.get("message") or body.get("result") or "ok")
        except Exception:
            message = "ok"
        return True, message
    except Exception as exc:
        return False, str(exc)


def ensure_rutracker_indexer(username: str, password: str, *, enable: bool = True) -> Dict[str, Any]:
    """Create or update RuTracker indexer credentials in Prowlarr."""
    try:
        if not username.strip() or not password.strip():
            return {"ok": False, "error": "username/password are required"}

        existing = _find_existing_rutracker()
        action = "updated"
        if existing:
            payload = _request("GET", f"/api/v1/indexer/{existing['id']}").json()
        else:
            action = "created"
            payload = deepcopy(_find_rutracker_schema())
            payload["name"] = "RuTracker.org"
            payload["enable"] = bool(enable)

        fields = payload.get("fields") or []
        _set_field(fields, "username", username.strip())
        _set_field(fields, "password", password.strip())
        payload["fields"] = fields
        payload["enable"] = bool(enable)

        if existing:
            indexer_id = existing["id"]
            saved = _request("PUT", f"/api/v1/indexer/{indexer_id}", json_data=payload).json()
        else:
            saved = _request("POST", "/api/v1/indexer", json_data=payload).json()
            indexer_id = saved.get("id")

        test_ok, test_message = _test_indexer(saved)
        return {
            "ok": True,
            "action": action,
            "id": indexer_id,
            "test_ok": test_ok,
            "test_message": test_message,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
