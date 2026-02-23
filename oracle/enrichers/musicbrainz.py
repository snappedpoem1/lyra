"""MusicBrainz metadata provider."""

from __future__ import annotations

from typing import Dict, Optional
import os
import time
import requests

from dotenv import load_dotenv

MB_BASE_URL = os.getenv("MB_BASE_URL", "https://musicbrainz.org/ws/2/")


def _user_agent() -> str:
    name = os.getenv("MB_APP_NAME", "LyraOracle")
    version = os.getenv("MB_APP_VERSION", "1.0")
    contact = os.getenv("MB_CONTACT", "unknown@example.com")
    return f"{name}/{version} ( {contact} )"


def _request(url: str, params: Dict[str, str]) -> Dict:
    headers = {"User-Agent": _user_agent()}
    for attempt in range(1, 4):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            time.sleep(float(os.getenv("MB_RATE_LIMIT_RPS", "1")))
            return response.json()
        except Exception:
            time.sleep(2 ** attempt)
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
