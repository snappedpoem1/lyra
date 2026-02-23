"""Discogs metadata provider."""

from __future__ import annotations

from typing import Dict, Optional
import os
import time
import requests

from dotenv import load_dotenv


def _headers() -> Dict[str, str]:
    token = os.getenv("DISCOGS_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCOGS_TOKEN")
    return {"Authorization": f"Discogs token={token}", "User-Agent": "LyraOracle/1.0"}


def _debug(message: str) -> None:
    if os.getenv("LYRA_DEBUG") == "1":
        print(message)


def search_release(artist: str, album: str, year: Optional[str] = None) -> Dict:
    params = {"artist": artist, "release_title": album, "per_page": 5}
    if year:
        params["year"] = year

    for attempt in range(1, 4):
        try:
            response = requests.get(
                "https://api.discogs.com/database/search",
                params=params,
                headers=_headers(),
                timeout=30
            )
            response.raise_for_status()
            time.sleep(1.0)
            payload = response.json()
            _debug(f"Discogs search status={response.status_code} attempt={attempt} items={payload.get('pagination', {}).get('items')}")
            return payload
        except Exception:
            time.sleep(2 ** attempt)
    return {}


def get_release_details(discogs_id: str) -> Dict:
    for attempt in range(1, 4):
        try:
            response = requests.get(
                f"https://api.discogs.com/releases/{discogs_id}",
                headers=_headers(),
                timeout=30
            )
            response.raise_for_status()
            time.sleep(1.0)
            payload = response.json()
            _debug(f"Discogs release status={response.status_code} attempt={attempt}")
            return payload
        except Exception:
            time.sleep(2 ** attempt)
    return {}


if __name__ == "__main__":
    load_dotenv(override=True)
    print("Discogs provider ready")
