"""Prowlarr + Real-Debrid acquisition backend."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import os
import re
import time
import requests

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = (PROJECT_ROOT / "downloads").resolve()
STAGING_DIR = (PROJECT_ROOT / "staging").resolve()

# Prowlarr audio subcategories focused on music releases:
#   3010 = Audio/MP3
#   3040 = Audio/Lossless
# Avoid broad 3000 to reduce noisy audio/video and miscellaneous results.
CATEGORY_IDS = [3010, 3040]


def _request(method: str, url: str, headers: Dict[str, str] | None = None, params=None, data=None, timeout: int = 30):
    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed: {last_error}")


def search_prowlarr(query: str, limit: int = 5) -> List[Dict]:
    base_url = os.getenv("PROWLARR_BASE_URL") or os.getenv("PROWLARR_URL", "http://localhost:9696")
    api_key = os.getenv("PROWLARR_API_KEY")
    if not api_key:
        raise RuntimeError("Missing PROWLARR_API_KEY")

    url = f"{base_url.rstrip('/')}/api/v1/search"
    params = {
        "query": query,
        "type": "search",
        "categories": CATEGORY_IDS,
        "limit": limit,
    }
    headers = {"X-Api-Key": api_key}

    response = _request("GET", url, headers=headers, params=params)
    results = response.json()
    if not results:
        # Fallback for indexers that only expose broad Audio category mappings.
        fallback_params = {
            "query": query,
            "type": "search",
            "categories": [3000],
            "limit": limit,
        }
        response = _request("GET", url, headers=headers, params=fallback_params)
        results = response.json()
    return results[:limit]


def add_to_real_debrid(magnet_or_torrent: str) -> str:
    api_key = os.getenv("REAL_DEBRID_API_KEY") or os.getenv("REAL_DEBRID_KEY")
    if not api_key:
        raise RuntimeError("Missing REAL_DEBRID_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}
    value = (magnet_or_torrent or "").strip()
    if not value:
        raise RuntimeError("Empty magnet/torrent input")

    # Preferred: direct magnet URI.
    if value.lower().startswith("magnet:?"):
        response = _request(
            "POST",
            "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
            headers=headers,
            data={"magnet": value},
        )
        return response.json().get("id")

    # Fallback: fetch torrent file or parse a page that contains a magnet.
    fetch_resp = requests.get(value, timeout=60, allow_redirects=False)
    if 300 <= fetch_resp.status_code < 400:
        redirect_to = (fetch_resp.headers.get("location") or "").strip()
        if redirect_to.lower().startswith("magnet:?"):
            response = _request(
                "POST",
                "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
                headers=headers,
                data={"magnet": redirect_to},
            )
            return response.json().get("id")
        if redirect_to:
            fetch_resp = _request("GET", redirect_to, timeout=60)
        else:
            fetch_resp.raise_for_status()
    else:
        fetch_resp.raise_for_status()
    ctype = (fetch_resp.headers.get("content-type") or "").lower()
    body = fetch_resp.content

    if "text/html" in ctype:
        text = fetch_resp.text
        match = re.search(r"(magnet:\?xt=urn:btih:[^\"'\\s<]+)", text, flags=re.IGNORECASE)
        if match:
            response = _request(
                "POST",
                "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
                headers=headers,
                data={"magnet": match.group(1)},
            )
            return response.json().get("id")
        raise RuntimeError("No magnet URI found in HTML page")

    # Assume torrent payload and upload as multipart.
    for attempt in range(1, 4):
        try:
            response = requests.post(
                "https://api.real-debrid.com/rest/1.0/torrents/addTorrent",
                headers=headers,
                files={"file": ("upload.torrent", body, "application/x-bittorrent")},
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("id")
        except Exception as exc:
            if attempt == 3:
                raise RuntimeError(f"Real-Debrid addTorrent failed: {exc}")
            time.sleep(2 ** attempt)
    return ""


def select_files(torrent_id: str) -> None:
    api_key = os.getenv("REAL_DEBRID_API_KEY") or os.getenv("REAL_DEBRID_KEY")
    if not api_key:
        raise RuntimeError("Missing REAL_DEBRID_API_KEY/REAL_DEBRID_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    _request(
        "POST",
        f"https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{torrent_id}",
        headers=headers,
        data={"files": "all"}
    )


def poll_real_debrid(torrent_id: str, max_wait: int = 300) -> Dict:
    api_key = os.getenv("REAL_DEBRID_API_KEY") or os.getenv("REAL_DEBRID_KEY")
    if not api_key:
        raise RuntimeError("Missing REAL_DEBRID_API_KEY/REAL_DEBRID_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    start = time.time()
    while time.time() - start < max_wait:
        response = _request(
            "GET",
            f"https://api.real-debrid.com/rest/1.0/torrents/info/{torrent_id}",
            headers=headers
        )
        info = response.json()
        status = info.get("status")
        if status in {"downloaded", "error", "dead"}:
            return info
        time.sleep(10)
    raise RuntimeError("Real-Debrid polling timed out")


def _download_file(url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with output.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return output


def download_from_real_debrid(torrent_id: str) -> List[Path]:
    api_key = os.getenv("REAL_DEBRID_API_KEY") or os.getenv("REAL_DEBRID_KEY")
    if not api_key:
        raise RuntimeError("Missing REAL_DEBRID_API_KEY/REAL_DEBRID_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    response = _request(
        "GET",
        f"https://api.real-debrid.com/rest/1.0/torrents/info/{torrent_id}",
        headers=headers
    )
    info = response.json()
    links = info.get("links", [])

    downloaded: List[Path] = []
    for link in links:
        unrestrict = _request(
            "POST",
            "https://api.real-debrid.com/rest/1.0/unrestrict/link",
            headers=headers,
            data={"link": link}
        ).json()

        filename = unrestrict.get("filename", "download.bin")
        url = unrestrict.get("download")
        if not url:
            continue

        target = DOWNLOAD_DIR / filename
        downloaded.append(_download_file(url, target))

    return downloaded


def move_to_staging(paths: List[Path]) -> List[Path]:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    moved: List[Path] = []
    for path in paths:
        target = STAGING_DIR / path.name
        if target.exists():
            target = STAGING_DIR / f"{path.stem}_{int(time.time())}{path.suffix}"
        moved.append(Path(path.rename(target)))
    return moved


if __name__ == "__main__":
    load_dotenv(override=True)
    print("Prowlarr/Real-Debrid backend ready")
