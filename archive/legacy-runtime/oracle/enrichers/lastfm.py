"""Last.fm metadata provider with retries and rate limiting."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

LASTFM_API_URL = os.getenv("LASTFM_API_URL", "https://ws.audioscrobbler.com/2.0/")
_REQUEST_TIMEOUT = float(os.getenv("LASTFM_TIMEOUT_SECONDS", "20"))
_MAX_RETRIES = int(os.getenv("LASTFM_MAX_RETRIES", "4"))
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MIN_INTERVAL_SECONDS = float(os.getenv("LASTFM_MIN_INTERVAL_SECONDS", "0.25"))

_SESSION = requests.Session()
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_TS = 0.0


def _api_key() -> str:
    return os.getenv("LASTFM_API_KEY", "").strip()


def _respect_rate_limit() -> None:
    global _LAST_REQUEST_TS
    with _RATE_LOCK:
        elapsed = time.monotonic() - _LAST_REQUEST_TS
        wait = max(0.0, _MIN_INTERVAL_SECONDS - elapsed)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_TS = time.monotonic()


def _request(method: str, params: Dict[str, str]) -> Dict[str, Any]:
    key = _api_key()
    if not key:
        logger.debug("LASTFM_API_KEY is missing; skipping Last.fm request")
        return {}

    query = {
        "method": method,
        "api_key": key,
        "format": "json",
    }
    query.update(params)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _respect_rate_limit()
            response = _SESSION.get(LASTFM_API_URL, params=query, timeout=_REQUEST_TIMEOUT)
            if response.status_code in _RETRYABLE_STATUS:
                base = min(16.0, 2 ** (attempt - 1))
                jitter = random.uniform(0.0, base * 0.3)
                time.sleep(base + jitter)
                continue
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("error"):
                return {}
            return data if isinstance(data, dict) else {}
        except requests.Timeout:
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** attempt))
        except requests.RequestException as exc:
            logger.debug("Last.fm request error (%s) on attempt %d", exc, attempt)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** (attempt - 1)))
    return {}


def _extract_tags(payload: Dict[str, Any], top_node: str = "toptags", limit: int = 5) -> List[str]:
    tags_node = payload.get(top_node, {})
    tags = tags_node.get("tag", []) if isinstance(tags_node, dict) else []
    if isinstance(tags, dict):
        tags = [tags]

    out: List[str] = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        name = str(tag.get("name", "")).strip().lower()
        if not name:
            continue
        if name in {"seen live", "favorites", "my favorite", "awesome"}:
            continue
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def track_get_info(artist: str, title: str, autocorrect: int = 1) -> Dict[str, Any]:
    return _request(
        "track.getInfo",
        {"artist": artist, "track": title, "autocorrect": str(autocorrect)},
    )


def track_get_top_tags(artist: str, title: str, autocorrect: int = 1) -> Dict[str, Any]:
    return _request(
        "track.getTopTags",
        {"artist": artist, "track": title, "autocorrect": str(autocorrect)},
    )


def artist_get_top_tags(artist: str, autocorrect: int = 1) -> Dict[str, Any]:
    return _request("artist.getTopTags", {"artist": artist, "autocorrect": str(autocorrect)})


def track_get_similar(artist: str, title: str, limit: int = 10) -> Dict[str, Any]:
    return _request(
        "track.getSimilar",
        {"artist": artist, "track": title, "limit": str(limit)},
    )


def artist_get_similar(artist: str, limit: int = 10) -> Dict[str, Any]:
    return _request("artist.getSimilar", {"artist": artist, "limit": str(limit)})


def build_track_profile(artist: str, title: str) -> Dict[str, Any]:
    """Return normalized Last.fm payload for one track."""
    if not artist or not title:
        return {}

    info_payload = track_get_info(artist, title)
    track_node = info_payload.get("track", {}) if isinstance(info_payload, dict) else {}

    tags = _extract_tags(track_node, "toptags", limit=5)
    if not tags:
        tags_payload = track_get_top_tags(artist, title)
        tags = _extract_tags(tags_payload, "toptags", limit=5)
    if not tags:
        artist_tags_payload = artist_get_top_tags(artist)
        tags = _extract_tags(artist_tags_payload, "toptags", limit=5)

    similar_tracks_payload = track_get_similar(artist, title, limit=10)
    similar_tracks_node = similar_tracks_payload.get("similartracks", {})
    similar_track_rows = similar_tracks_node.get("track", []) if isinstance(similar_tracks_node, dict) else []
    if isinstance(similar_track_rows, dict):
        similar_track_rows = [similar_track_rows]

    similar_tracks: List[Dict[str, str]] = []
    for row in similar_track_rows[:10]:
        if not isinstance(row, dict):
            continue
        sim_name = str(row.get("name", "")).strip()
        sim_artist_node = row.get("artist", {})
        if isinstance(sim_artist_node, dict):
            sim_artist = str(sim_artist_node.get("name", "")).strip()
        else:
            sim_artist = str(sim_artist_node or "").strip()
        if sim_name:
            similar_tracks.append({"artist": sim_artist, "title": sim_name})

    artist_sim_payload = artist_get_similar(artist, limit=10)
    artist_sim_node = artist_sim_payload.get("similarartists", {})
    artist_rows = artist_sim_node.get("artist", []) if isinstance(artist_sim_node, dict) else []
    if isinstance(artist_rows, dict):
        artist_rows = [artist_rows]
    similar_artists = [
        str(row.get("name", "")).strip()
        for row in artist_rows[:10]
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]

    wiki_node = track_node.get("wiki", {}) if isinstance(track_node, dict) else {}
    summary = str(wiki_node.get("summary", "")).strip() if isinstance(wiki_node, dict) else ""
    if "<a href=" in summary:
        summary = summary.split("<a href=", 1)[0].strip()

    return {
        "provider": "lastfm",
        "artist": artist,
        "title": title,
        "listeners": track_node.get("listeners"),
        "playcount": track_node.get("playcount"),
        "duration": track_node.get("duration"),
        "tags": tags,
        "similar_tracks": similar_tracks,
        "similar_artists": similar_artists,
        "summary": summary,
        "url": track_node.get("url"),
    }
