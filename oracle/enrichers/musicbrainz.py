"""MusicBrainz metadata provider."""

from __future__ import annotations

from typing import Dict, Optional
import logging
import os
import time
import requests

from dotenv import load_dotenv

MB_BASE_URL = os.getenv("MB_BASE_URL", "https://musicbrainz.org/ws/2/")
_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MB_TIMEOUT_SECONDS", "30"))
_MAX_RETRIES = int(os.getenv("MB_MAX_RETRIES", "4"))
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_LAST_REQUEST_TS = 0.0
_SESSION = requests.Session()
logger = logging.getLogger(__name__)


def _user_agent() -> str:
    name = os.getenv("MB_APP_NAME", "LyraOracle")
    version = os.getenv("MB_APP_VERSION", "1.0")
    contact = os.getenv("MB_CONTACT", "unknown@example.com")
    return f"{name}/{version} ({contact})"


def _min_interval_seconds() -> float:
    interval = os.getenv("MB_MIN_INTERVAL_SECONDS")
    if interval:
        try:
            return max(0.0, float(interval))
        except ValueError:
            return 1.1
    # Backward compatibility: existing env var name suggests RPS.
    # If MB_RATE_LIMIT_RPS=1, this enforces 1.0s between requests.
    rps = os.getenv("MB_RATE_LIMIT_RPS", "1")
    try:
        rate = max(0.1, float(rps))
    except ValueError:
        rate = 1.0
    return 1.0 / rate


def _respect_rate_limit() -> None:
    global _LAST_REQUEST_TS
    min_interval = _min_interval_seconds()
    elapsed = time.monotonic() - _LAST_REQUEST_TS
    wait = max(0.0, min_interval - elapsed)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_TS = time.monotonic()


def _retry_after_seconds(response: requests.Response) -> float:
    retry_after = response.headers.get("Retry-After", "").strip()
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return 0.0


def _request(url: str, params: Dict[str, str]) -> Dict:
    headers = {"User-Agent": _user_agent()}
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _respect_rate_limit()
            response = _SESSION.get(url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT_SECONDS)
            if response.status_code in _RETRYABLE_STATUS:
                server_wait = _retry_after_seconds(response)
                backoff_wait = min(16.0, 2 ** (attempt - 1))
                time.sleep(max(server_wait, backoff_wait))
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if attempt >= _MAX_RETRIES:
                logger.warning("MusicBrainz request failed after %s attempts: %s", attempt, exc)
                return {}
            time.sleep(min(16.0, 2 ** (attempt - 1)))
    return {}


def search_recording(artist: str, title: str, album: Optional[str] = None, duration: Optional[float] = None) -> Dict:
    query = f"recording:{title} AND artist:{artist}"
    if album:
        query += f" AND release:{album}"
    params = {"query": query, "fmt": "json"}
    if duration:
        params["dur"] = str(int(duration * 1000))
    return _request(f"{MB_BASE_URL.rstrip('/')}/recording", params)


def get_recording_details(mbid: str) -> Dict:
    params = {"fmt": "json", "inc": "artists+releases+tags"}
    return _request(f"{MB_BASE_URL.rstrip('/')}/recording/{mbid}", params)


def search_artist(name: str, limit: int = 5) -> Dict:
    """Search for an artist by name.

    Returns:
        Dict with 'artists' list, each having 'id', 'name', 'type',
        'disambiguation', 'score'.
    """
    params = {"query": f'artist:"{name}"', "fmt": "json", "limit": str(limit)}
    return _request(f"{_base()}/artist", params)


def get_release_groups(
    artist_mbid: str,
    release_type: str = "album",
    offset: int = 0,
    limit: int = 100,
) -> Dict:
    """Get release groups (albums/EPs/singles) for an artist.

    Args:
        artist_mbid: MusicBrainz artist ID.
        release_type: One of album, ep, single.
        offset: Pagination offset.
        limit: Max results per page.

    Returns:
        Dict with 'release-groups' list.
    """
    params = {
        "artist": artist_mbid,
        "type": release_type,
        "fmt": "json",
        "offset": str(offset),
        "limit": str(limit),
    }
    return _request(f"{_base()}/release-group", params)


def get_releases_for_group(release_group_mbid: str) -> Dict:
    """Get releases (with recordings/tracks) for a release group.

    Returns:
        Dict with 'releases' list, each containing 'media' with 'tracks'.
    """
    params = {
        "release-group": release_group_mbid,
        "inc": "recordings+artist-credits",
        "fmt": "json",
        "limit": "50",
    }
    return _request(f"{_base()}/release", params)


def _base() -> str:
    """Return base URL without trailing slash."""
    return MB_BASE_URL.rstrip("/")


if __name__ == "__main__":
    load_dotenv(override=True)
    print(search_recording("Radiohead", "Creep"))
