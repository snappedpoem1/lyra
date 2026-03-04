"""Discogs metadata provider."""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_RETRYABLE = {429, 500, 502, 503, 504}


def _headers() -> Dict[str, str]:
    token = os.getenv("DISCOGS_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCOGS_TOKEN")
    return {"Authorization": f"Discogs token={token}", "User-Agent": "LyraOracle/1.0"}


def _request_with_retry(url: str, params: Optional[Dict] = None, max_attempts: int = 3) -> Optional[Dict]:
    """Make a GET request with retry on transient errors only."""
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, params=params, headers=_headers(), timeout=30)
            if response.status_code in _RETRYABLE:
                backoff = min(16.0, 2 ** attempt)
                logger.warning("Discogs %d on attempt %d, retrying in %.0fs", response.status_code, attempt, backoff)
                time.sleep(backoff)
                continue
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            time.sleep(1.0)  # Discogs rate limit: 60 req/min
            return response.json()
        except requests.exceptions.Timeout:
            logger.warning("Discogs timeout on attempt %d", attempt)
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Discogs connection error on attempt %d: %s", attempt, exc)
            time.sleep(2 ** attempt)
        except requests.exceptions.HTTPError as exc:
            logger.error("Discogs HTTP error (non-retryable): %s", exc)
            return {}
    logger.error("Discogs request failed after %d attempts: %s", max_attempts, url)
    return {}


def search_release(artist: str, album: str, year: Optional[str] = None) -> Dict:
    """Search Discogs for a release."""
    params: Dict[str, str] = {"artist": artist, "release_title": album, "per_page": "5"}
    if year:
        params["year"] = year
    return _request_with_retry("https://api.discogs.com/database/search", params=params) or {}


def get_release_details(discogs_id: str) -> Dict:
    """Get detailed release info from Discogs."""
    return _request_with_retry(f"https://api.discogs.com/releases/{discogs_id}") or {}


if __name__ == "__main__":
    load_dotenv(override=True)
    print("Discogs provider ready")
