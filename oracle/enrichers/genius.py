"""Genius metadata provider with retries and candidate scoring."""

from __future__ import annotations

import logging
import os
import random
import re
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GENIUS_API_URL = os.getenv("GENIUS_API_URL", "https://api.genius.com")
_REQUEST_TIMEOUT = float(os.getenv("GENIUS_TIMEOUT_SECONDS", "20"))
_MAX_RETRIES = int(os.getenv("GENIUS_MAX_RETRIES", "4"))
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_SESSION = requests.Session()


def _token() -> str:
    return (
        os.getenv("GENIUS_ACCESS_TOKEN", "").strip()
        or os.getenv("GENIUS_TOKEN", "").strip()
    )


def _norm(text: str) -> str:
    value = (text or "").lower().strip()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\[[^\]]*\]", "", value)
    value = re.sub(r"\s*\((feat|ft)\.?.*?\)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*(radio edit|edit|remaster(ed)?|album version|single version)$", "", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _request(path: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    token = _token()
    if not token:
        logger.debug("GENIUS_ACCESS_TOKEN is missing; skipping Genius request")
        return {}

    url = f"{GENIUS_API_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}
    params = params or {}

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _SESSION.get(url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT)
            if response.status_code in _RETRYABLE_STATUS:
                base = min(16.0, 2 ** (attempt - 1))
                jitter = random.uniform(0.0, base * 0.3)
                time.sleep(base + jitter)
                continue
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return {}
            response_node = payload.get("response", {})
            return response_node if isinstance(response_node, dict) else {}
        except requests.Timeout:
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** attempt))
        except requests.RequestException as exc:
            logger.debug("Genius request error (%s) on attempt %d", exc, attempt)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** (attempt - 1)))
    return {}


def search(query: str, per_page: int = 5) -> List[Dict[str, Any]]:
    data = _request("/search", params={"q": query, "per_page": str(per_page)})
    hits = data.get("hits", []) if isinstance(data, dict) else []
    if not isinstance(hits, list):
        return []
    songs: List[Dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        result = hit.get("result")
        if isinstance(result, dict):
            songs.append(result)
    return songs


def get_song(song_id: int, text_format: str = "plain") -> Dict[str, Any]:
    params = {"text_format": text_format}
    data = _request(f"/songs/{int(song_id)}", params=params)
    song = data.get("song", {}) if isinstance(data, dict) else {}
    return song if isinstance(song, dict) else {}


def get_artist(artist_id: int, text_format: str = "plain") -> Dict[str, Any]:
    params = {"text_format": text_format}
    data = _request(f"/artists/{int(artist_id)}", params=params)
    artist = data.get("artist", {}) if isinstance(data, dict) else {}
    return artist if isinstance(artist, dict) else {}


def _pick_best_hit(hits: List[Dict[str, Any]], artist: str, title: str) -> Optional[Dict[str, Any]]:
    if not hits:
        return None
    best_hit: Optional[Dict[str, Any]] = None
    best_score = -1.0
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        hit_title = str(hit.get("title", "")).strip()
        primary_artist = hit.get("primary_artist", {})
        hit_artist = ""
        if isinstance(primary_artist, dict):
            hit_artist = str(primary_artist.get("name", "")).strip()

        title_score = _ratio(hit_title, title)
        artist_score = _ratio(hit_artist, artist)
        score = (title_score * 0.65) + (artist_score * 0.35)
        if score > best_score:
            best_score = score
            best_hit = hit
    if best_score < 0.55:
        return None
    return best_hit


def build_song_profile(artist: str, title: str) -> Dict[str, Any]:
    """Search and normalize Genius metadata for one song."""
    if not artist or not title:
        return {}

    query_title = _norm(title)
    query = f"{artist} {query_title or title}".strip()
    hits = search(query, per_page=10)
    best = _pick_best_hit(hits, artist=artist, title=title)
    if not best:
        return {}

    song_id = best.get("id")
    if not song_id:
        return {}
    song = get_song(int(song_id), text_format="plain")
    if not song:
        song = best

    primary_artist = song.get("primary_artist", {})
    artist_name = str(primary_artist.get("name", "")).strip() if isinstance(primary_artist, dict) else ""
    stats = song.get("stats", {}) if isinstance(song.get("stats"), dict) else {}
    desc = song.get("description", {}) if isinstance(song.get("description"), dict) else {}
    desc_plain = str(desc.get("plain", "")).strip()
    if len(desc_plain) > 1000:
        desc_plain = desc_plain[:1000].rstrip() + "..."

    return {
        "provider": "genius",
        "artist": artist_name or artist,
        "title": str(song.get("title", "")).strip() or title,
        "song_id": song.get("id"),
        "url": song.get("url"),
        "release_date": song.get("release_date"),
        "annotation_count": song.get("annotation_count"),
        "lyrics_state": song.get("lyrics_state"),
        "pageviews": stats.get("pageviews"),
        "hot": stats.get("hot"),
        "description": desc_plain,
        "song_art_image_url": song.get("song_art_image_url"),
    }
