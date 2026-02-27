"""Real-Debrid direct API integration.

Handles the full flow:
1. Check instant availability (cache)
2. Add magnet/torrent
3. Select files
4. Poll for completion
5. Unrestrict links
6. Download files

No qBittorrent or RDT-Client needed - direct API calls.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = (PROJECT_ROOT / "downloads").resolve()

# Real-Debrid API
RD_API_BASE = "https://api.real-debrid.com/rest/1.0"


def _get_api_key() -> str:
    """Get Real-Debrid API key from environment."""
    key = os.getenv("REAL_DEBRID_KEY") or os.getenv("REAL_DEBRID_API_KEY")
    if not key:
        raise RuntimeError("Missing REAL_DEBRID_KEY in environment")
    return key


def _headers() -> Dict[str, str]:
    """Get auth headers for RD API."""
    return {"Authorization": f"Bearer {_get_api_key()}"}


def _request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    params: Optional[Dict] = None,
    timeout: int = 30,
    retries: int = 3,
) -> requests.Response:
    """Make authenticated request to Real-Debrid API with retry."""
    url = f"{RD_API_BASE}{endpoint}"
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=_headers(),
                data=data,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            # Don't retry on 4xx errors (bad request, auth issues, etc.)
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise
            last_error = e
        except Exception as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Real-Debrid API request failed: {last_error}")


def check_instant_availability(hashes: List[str]) -> Dict[str, bool]:
    """Check if torrents are cached (instant availability).

    NOTE: Real-Debrid deprecated the /torrents/instantAvailability endpoint in
    2024 — it now returns 403 for all requests.  This function is kept for
    interface compatibility but always returns unknown (None-equivalent False).
    T1 acquisition now uses probe_magnet_cached() instead.

    Args:
        hashes: List of info hashes (lowercase)

    Returns:
        Dict mapping hash -> False (all unknown)
    """
    return {h.lower(): False for h in hashes}


def delete_torrent(torrent_id: str) -> None:
    """Delete a torrent from Real-Debrid (frees the slot).

    Args:
        torrent_id: RD torrent ID
    """
    try:
        _request("DELETE", f"/torrents/delete/{torrent_id}")
        logger.debug(f"Deleted torrent {torrent_id} from RD")
    except Exception as e:
        logger.debug(f"Delete torrent {torrent_id} failed (may already be gone): {e}")


_AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma"}
# Reject anything above this — discographies and multi-album dumps
_MAX_TORRENT_BYTES = 3 * 1024 ** 3  # 3 GB


def _find_best_file_id(files: List[Dict], artist: str, title: str) -> Optional[str]:
    """Return the RD file ID whose filename best matches artist + title.

    Only considers audio files.  Returns None if no confident match is found
    (caller should fall back to selecting all audio files).
    """
    from difflib import SequenceMatcher

    target = f"{artist} {title}".lower()
    best_score = 0.0
    best_id: Optional[str] = None

    for f in files:
        fpath = f.get("path", "")
        if Path(fpath).suffix.lower() not in _AUDIO_EXTENSIONS:
            continue
        stem = Path(fpath).stem.lower()
        score = SequenceMatcher(None, target, stem).ratio()
        if score > best_score:
            best_score = score
            best_id = str(f.get("id", ""))

    # Require at least 40% overlap — prevents false positives on big albums
    return best_id if best_score >= 0.40 else None


def probe_magnet_cached(
    magnet: str,
    target_artist: str = "",
    target_title: str = "",
    file_select_wait: int = 12,
    download_wait: int = 20,
    poll_interval: int = 2,
) -> Optional[List[Path]]:
    """Add a magnet to RD, probe cache status, download only the target file.

    Real-Debrid's instantAvailability endpoint is deprecated (403).  The only
    reliable test is to add the magnet, wait for file-selection, inspect the
    file list, then poll for completion:

    - Reaches "waiting_files_selection" quickly (both cached and uncached).
    - Selects only the best-matching audio file (not the whole torrent).
    - Reaches "downloaded" within seconds if cached → return files.
    - Still downloading after download_wait → not cached → delete and return None.

    Safety checks (all trigger a delete + None):
    - Total torrent > 3 GB  (discography / multi-album dump)
    - Never reaches file-selection within file_select_wait seconds
    - Never reaches "downloaded" within download_wait seconds after selection

    Args:
        magnet:            Magnet URI
        target_artist:     Expected artist (for file matching)
        target_title:      Expected title  (for file matching)
        file_select_wait:  Seconds to wait for "waiting_files_selection" status
        download_wait:     Seconds to wait for "downloaded" after file selection
        poll_interval:     Seconds between status polls

    Returns:
        List of downloaded Paths if cached, None otherwise
    """
    torrent_id = None
    try:
        torrent_id = add_magnet(magnet)

        # ── Phase 1: wait for file list ──────────────────────────────────────
        selected = False
        start = time.time()
        while time.time() - start < file_select_wait:
            info = get_torrent_info(torrent_id)
            status = info.get("status", "")

            if status in ("error", "dead", "magnet_error", "virus"):
                logger.debug(f"[RD] Torrent {torrent_id} bad status: {status}")
                delete_torrent(torrent_id)
                return None

            if status == "waiting_files_selection":
                files = info.get("files", [])
                total_bytes = sum(f.get("bytes", 0) for f in files)

                if total_bytes > _MAX_TORRENT_BYTES:
                    gb = total_bytes / 1024 ** 3
                    logger.debug(f"[RD] Torrent too large ({gb:.1f} GB) — skipping")
                    delete_torrent(torrent_id)
                    return None

                # Try to find the specific track; fall back to all audio
                file_id = _find_best_file_id(files, target_artist, target_title)
                if file_id:
                    logger.debug(f"[RD] Selecting file id={file_id} for '{target_artist} - {target_title}'")
                    select_files(torrent_id, file_id)
                else:
                    select_files(torrent_id, "all")

                selected = True
                break

            # "downloaded" can appear before file-selection on some edge cases
            if status == "downloaded":
                return download_torrent_files(torrent_id, audio_only=True)

            time.sleep(poll_interval)

        if not selected:
            # Never reached file-selection → not cached / magnet resolution failed
            logger.debug(f"[RD] No file list within {file_select_wait}s — not cached")
            delete_torrent(torrent_id)
            return None

        # ── Phase 2: wait for download ────────────────────────────────────────
        start = time.time()
        while time.time() - start < download_wait:
            info = get_torrent_info(torrent_id)
            status = info.get("status", "")

            if status == "downloaded":
                logger.info(f"[RD] Cached hit — torrent {torrent_id}")
                return download_torrent_files(torrent_id, audio_only=True)

            if status in ("error", "dead", "magnet_error", "virus"):
                logger.debug(f"[RD] Torrent {torrent_id} failed after selection: {status}")
                delete_torrent(torrent_id)
                return None

            time.sleep(poll_interval)

        # Timed out after selection → not cached
        logger.debug(f"[RD] Torrent {torrent_id} not downloaded in {download_wait}s — not cached")
        delete_torrent(torrent_id)
        return None

    except Exception as exc:
        logger.debug(f"[RD] probe_magnet_cached failed: {exc}")
        if torrent_id:
            delete_torrent(torrent_id)
        return None


def extract_hash_from_magnet(magnet: str) -> Optional[str]:
    """Extract info hash from magnet URI."""
    match = re.search(r"btih:([a-fA-F0-9]{40})", magnet)
    if match:
        return match.group(1).lower()
    # Also handle base32 encoded hashes
    match = re.search(r"btih:([a-zA-Z2-7]{32})", magnet)
    if match:
        import base64
        try:
            decoded = base64.b32decode(match.group(1).upper())
            return decoded.hex().lower()
        except Exception:
            pass
    return None


def add_magnet(magnet: str) -> str:
    """Add a magnet to Real-Debrid.

    Returns:
        Torrent ID
    """
    response = _request("POST", "/torrents/addMagnet", data={"magnet": magnet})
    data = response.json()
    torrent_id = data.get("id")
    if not torrent_id:
        raise RuntimeError("Real-Debrid returned no torrent ID")
    logger.info(f"Added magnet to RD: {torrent_id}")
    return torrent_id


def add_torrent_file(torrent_bytes: bytes) -> str:
    """Upload a torrent file to Real-Debrid.

    Returns:
        Torrent ID
    """
    response = requests.put(
        f"{RD_API_BASE}/torrents/addTorrent",
        headers=_headers(),
        data=torrent_bytes,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    torrent_id = data.get("id")
    if not torrent_id:
        raise RuntimeError("Real-Debrid returned no torrent ID")
    logger.info(f"Added torrent file to RD: {torrent_id}")
    return torrent_id


def select_files(torrent_id: str, file_ids: str = "all") -> None:
    """Select files to download from a torrent.

    Args:
        torrent_id: RD torrent ID
        file_ids: Comma-separated file IDs or "all"
    """
    _request("POST", f"/torrents/selectFiles/{torrent_id}", data={"files": file_ids})
    logger.info(f"Selected files for torrent {torrent_id}: {file_ids}")


def get_torrent_info(torrent_id: str) -> Dict[str, Any]:
    """Get info about a torrent."""
    response = _request("GET", f"/torrents/info/{torrent_id}")
    return response.json()


def poll_until_ready(torrent_id: str, max_wait: int = 300, poll_interval: int = 5) -> Dict[str, Any]:
    """Poll torrent until downloaded or failed.

    Args:
        torrent_id: RD torrent ID
        max_wait: Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        Final torrent info dict
    """
    start = time.time()
    while time.time() - start < max_wait:
        info = get_torrent_info(torrent_id)
        status = info.get("status")

        if status == "downloaded":
            logger.info(f"Torrent {torrent_id} ready")
            return info
        elif status in ("error", "dead", "magnet_error"):
            raise RuntimeError(f"Torrent failed: {status}")
        elif status == "waiting_files_selection":
            # Need to select files
            select_files(torrent_id)
        else:
            logger.debug(f"Torrent {torrent_id} status: {status} ({info.get('progress', 0)}%)")

        time.sleep(poll_interval)

    raise RuntimeError(f"Torrent {torrent_id} timed out after {max_wait}s")


def unrestrict_link(link: str) -> Dict[str, Any]:
    """Unrestrict a link to get direct download URL.

    Returns:
        Dict with 'download' (direct URL), 'filename', 'filesize', etc.
    """
    response = _request("POST", "/unrestrict/link", data={"link": link})
    return response.json()


def download_file(url: str, output_path: Path, chunk_size: int = 1024 * 1024) -> Path:
    """Download a file from URL.

    Args:
        url: Direct download URL
        output_path: Where to save the file
        chunk_size: Download chunk size (default 1MB)

    Returns:
        Path to downloaded file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with output_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

    logger.info(f"Downloaded: {output_path}")
    return output_path


def download_torrent_files(
    torrent_id: str,
    output_dir: Optional[Path] = None,
    audio_only: bool = True,
) -> List[Path]:
    """Download all files from a completed torrent.

    Args:
        torrent_id: RD torrent ID
        output_dir: Where to save files (default: downloads folder)
        audio_only: Only download audio files

    Returns:
        List of downloaded file paths
    """
    output_dir = output_dir or DOWNLOAD_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    info = get_torrent_info(torrent_id)
    links = info.get("links", [])

    if not links:
        raise RuntimeError(f"No links found for torrent {torrent_id}")

    audio_extensions = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma"}
    downloaded: List[Path] = []

    for link in links:
        try:
            unrestricted = unrestrict_link(link)
            download_url = unrestricted.get("download")
            filename = unrestricted.get("filename", "download.bin")

            if not download_url:
                logger.warning(f"No download URL for link: {link}")
                continue

            # Filter audio files if requested
            ext = Path(filename).suffix.lower()
            if audio_only and ext not in audio_extensions:
                logger.debug(f"Skipping non-audio file: {filename}")
                continue

            output_path = output_dir / filename
            downloaded.append(download_file(download_url, output_path))

        except Exception as e:
            logger.error(f"Failed to download link: {e}")

    return downloaded


def acquire_from_magnet(
    magnet: str,
    output_dir: Optional[Path] = None,
    audio_only: bool = True,
    max_wait: int = 300,
) -> List[Path]:
    """Full acquisition flow from magnet to downloaded files.

    Args:
        magnet: Magnet URI
        output_dir: Where to save files
        audio_only: Only download audio files
        max_wait: Max seconds to wait for torrent

    Returns:
        List of downloaded file paths
    """
    # Check if cached first
    info_hash = extract_hash_from_magnet(magnet)
    if info_hash:
        availability = check_instant_availability([info_hash])
        if availability.get(info_hash):
            logger.info("Torrent is cached (instant availability)")

    # Add magnet
    torrent_id = add_magnet(magnet)

    # Select all files
    select_files(torrent_id)

    # Wait for completion
    poll_until_ready(torrent_id, max_wait=max_wait)

    # Download files
    return download_torrent_files(torrent_id, output_dir, audio_only)


if __name__ == "__main__":
    load_dotenv(override=True)
    logging.basicConfig(level=logging.INFO)

    # Test API connection
    try:
        response = _request("GET", "/user")
        user = response.json()
        print(f"Connected to Real-Debrid as: {user.get('username')}")
        print(f"Premium: {user.get('premium', 0)} days remaining")
    except Exception as e:
        print(f"Failed to connect: {e}")
