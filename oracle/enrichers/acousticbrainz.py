"""AcousticBrainz high-level descriptors provider.

AcousticBrainz is built from Essentia models and provides mood/genre descriptors
for MusicBrainz recording IDs.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ACOUSTICBRAINZ_API_URL = os.getenv("ACOUSTICBRAINZ_API_URL", "https://acousticbrainz.org")
_REQUEST_TIMEOUT = float(os.getenv("ACOUSTICBRAINZ_TIMEOUT_SECONDS", "20"))
_MAX_RETRIES = int(os.getenv("ACOUSTICBRAINZ_MAX_RETRIES", "3"))
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_SESSION = requests.Session()


def _request(path: str) -> Dict[str, Any]:
    url = f"{ACOUSTICBRAINZ_API_URL.rstrip('/')}/{path.lstrip('/')}"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _SESSION.get(url, timeout=_REQUEST_TIMEOUT)
            if response.status_code in _RETRYABLE_STATUS:
                base = min(16.0, 2 ** (attempt - 1))
                jitter = random.uniform(0.0, base * 0.3)
                time.sleep(base + jitter)
                continue
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except requests.Timeout:
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** attempt))
        except requests.RequestException as exc:
            logger.debug("AcousticBrainz request error (%s) on attempt %d", exc, attempt)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** (attempt - 1)))
    return {}


def _extract_tags(payload: Dict[str, Any], limit: int = 8) -> List[str]:
    high = payload.get("highlevel", {}) if isinstance(payload, dict) else {}
    if not isinstance(high, dict):
        return []

    tags: List[str] = []
    for node_name, node in high.items():
        if not isinstance(node, dict):
            continue
        value = str(node.get("value", "")).strip().lower()
        if not value:
            continue
        if node_name.startswith("genre_") or node_name.startswith("mood_"):
            if value not in tags:
                tags.append(value)
        if len(tags) >= limit:
            break
    return tags


def _extract_mood_scores(payload: Dict[str, Any]) -> Dict[str, float]:
    high = payload.get("highlevel", {}) if isinstance(payload, dict) else {}
    if not isinstance(high, dict):
        return {}

    out: Dict[str, float] = {}
    for key in ("mood_aggressive", "mood_happy", "mood_sad", "mood_relaxed", "mood_party"):
        node = high.get(key)
        if not isinstance(node, dict):
            continue
        probs = node.get("all", {})
        if not isinstance(probs, dict):
            continue
        # Normalize to probability of the "positive" class if present.
        for candidate in ("aggressive", "happy", "sad", "relaxed", "party"):
            if candidate in probs:
                try:
                    out[key] = float(probs[candidate])
                except (TypeError, ValueError):
                    pass
                break
    return out


def build_track_profile(
    artist: str,
    title: str,
    recording_mbid: Optional[str] = None,
    album: Optional[str] = None,
    duration: Optional[float] = None,
) -> Dict[str, Any]:
    """Return normalized AcousticBrainz payload for one track."""
    mbid = (recording_mbid or "").strip()
    if not mbid and artist and title:
        try:
            from oracle.enrichers import musicbrainz

            mb_payload = musicbrainz.search_recording(artist, title, album, duration)
            if isinstance(mb_payload, dict):
                mbid = str(mb_payload.get("recording_mbid") or mb_payload.get("id") or "").strip()
        except Exception as exc:
            logger.debug("AcousticBrainz MBID lookup failed: %s", exc)

    if not mbid:
        return {}

    payload = _request(f"{mbid}/high-level")
    if not payload:
        return {}

    tags = _extract_tags(payload)
    moods = _extract_mood_scores(payload)

    return {
        "provider": "acousticbrainz",
        "artist": artist,
        "title": title,
        "recording_mbid": mbid,
        "tags": tags,
        "mood_scores": moods,
        "url": f"{ACOUSTICBRAINZ_API_URL.rstrip('/')}/{mbid}/high-level",
    }

