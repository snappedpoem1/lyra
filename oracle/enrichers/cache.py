"""Provider response cache helpers backed by enrich_cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any, Dict, Optional

from oracle.db.schema import get_connection


def make_lookup_key(*parts: object) -> str:
    """Build a stable, short lookup key from arbitrary parts."""
    normalized = []
    for part in parts:
        text = str(part or "").strip().lower()
        text = " ".join(text.split())
        normalized.append(text)
    raw = "|".join(normalized)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_cached_payload(
    provider: str,
    lookup_key: str,
    max_age_seconds: int = 0,
) -> Optional[Dict[str, Any]]:
    """Return cached payload or None when absent/stale/invalid."""
    attempts = 3
    for attempt in range(1, attempts + 1):
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT payload_json, fetched_at
                FROM enrich_cache
                WHERE provider = ? AND lookup_key = ?
                """,
                (provider, lookup_key),
            )
            row = cursor.fetchone()
            if not row:
                return None

            payload_json, fetched_at = row
            if (
                max_age_seconds > 0
                and fetched_at is not None
                and (time.time() - float(fetched_at)) > float(max_age_seconds)
            ):
                return None

            if not payload_json:
                return None

            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                return None
            return payload
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < attempts:
                time.sleep(0.03 * attempt)
                continue
            return None
        except Exception:
            return None
        finally:
            conn.close()
    return None


def set_cached_payload(provider: str, lookup_key: str, payload: Dict[str, Any]) -> None:
    """Upsert payload into enrich_cache."""
    attempts = 5
    for attempt in range(1, attempts + 1):
        conn = get_connection(timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
                VALUES (?, ?, ?, ?)
                """,
                (provider, lookup_key, json.dumps(payload), time.time()),
            )
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < attempts:
                time.sleep(0.05 * attempt)
                continue
            return
        finally:
            conn.close()


def get_or_set_payload(
    provider: str,
    lookup_key: str,
    max_age_seconds: int,
    fetcher,
    miss_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return cached payload when fresh, otherwise fetch and cache it."""
    cached = get_cached_payload(provider, lookup_key, max_age_seconds=max_age_seconds)
    if cached is not None:
        return cached

    payload = fetcher()
    if payload is None:
        payload = miss_payload or {"_miss": True}
    if not isinstance(payload, dict):
        payload = {"_miss": True}
    set_cached_payload(provider, lookup_key, payload)
    return payload
