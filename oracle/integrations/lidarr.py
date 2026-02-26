"""Lidarr integration -- artist monitoring and release discovery.

Lidarr watches artists for new releases and populates Oracle's
``acquisition_queue`` with wanted tracks. It does NOT download directly --
the existing waterfall pipeline handles all acquisition.

Requires:
    LIDARR_URL and LIDARR_API_KEY in .env
    Lidarr Docker container (lyra_lidarr) running on port 8686
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def _base_url() -> str:
    return (os.getenv("LIDARR_URL") or "http://localhost:8686").rstrip("/")


def _api_key() -> str:
    return (os.getenv("LIDARR_API_KEY") or "").strip()


def _headers() -> Dict[str, str]:
    return {"X-Api-Key": _api_key()}


def _get(path: str, params: Optional[Dict] = None) -> Any:
    """Make a GET request to Lidarr API v1."""
    url = f"{_base_url()}/api/v1/{path.lstrip('/')}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, json_data: Any = None) -> Any:
    """Make a POST request to Lidarr API v1."""
    url = f"{_base_url()}/api/v1/{path.lstrip('/')}"
    resp = requests.post(url, headers=_headers(), json=json_data, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Check if Lidarr is reachable and API key is configured."""
    if not _api_key():
        return False
    try:
        url = f"{_base_url()}/api/v1/system/status"
        resp = requests.get(url, headers=_headers(), timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def get_status() -> Dict[str, Any]:
    """Return Lidarr system status."""
    return _get("system/status")


def get_artists() -> List[Dict[str, Any]]:
    """Return all monitored artists."""
    return _get("artist")


def add_artist(
    name: str,
    musicbrainz_id: Optional[str] = None,
    monitor: str = "all",
    quality_profile_id: int = 1,
    metadata_profile_id: int = 1,
    root_folder_path: str = "/downloads",
) -> Dict[str, Any]:
    """Add an artist to Lidarr for monitoring.

    Args:
        name: Artist name.
        musicbrainz_id: MusicBrainz artist ID (optional, Lidarr will search).
        monitor: Monitoring mode -- "all", "future", "missing", "none".
        quality_profile_id: Lidarr quality profile ID.
        metadata_profile_id: Lidarr metadata profile ID.
        root_folder_path: Root folder for downloads inside container.

    Returns:
        Lidarr artist response.
    """
    # Search Lidarr for the artist first to get foreignArtistId
    if not musicbrainz_id:
        search_results = _get("artist/lookup", params={"term": name})
        if not search_results:
            raise ValueError(f"Lidarr could not find artist: {name}")
        # Pick best match
        best = search_results[0]
        musicbrainz_id = best.get("foreignArtistId", "")

    payload = {
        "artistName": name,
        "foreignArtistId": musicbrainz_id,
        "qualityProfileId": quality_profile_id,
        "metadataProfileId": metadata_profile_id,
        "rootFolderPath": root_folder_path,
        "monitored": True,
        "monitorNewItems": monitor,
        "addOptions": {
            "monitor": monitor,
            "searchForMissingAlbums": False,
        },
    }
    return _post("artist", json_data=payload)


def get_wanted(limit: int = 50) -> List[Dict[str, Any]]:
    """Return wanted/missing albums from Lidarr.

    Returns:
        List of album dicts with artist info and track lists.
    """
    data = _get("wanted/missing", params={
        "pageSize": limit,
        "sortKey": "releaseDate",
        "sortDirection": "descending",
    })
    records = data.get("records", [])
    return records


def get_album_tracks(album_id: int) -> List[Dict[str, Any]]:
    """Return tracks for a specific album."""
    return _get("track", params={"albumId": album_id})


def sync_wanted_to_queue(limit: int = 50, dry_run: bool = False) -> Dict[str, int]:
    """Pull wanted tracks from Lidarr and insert into acquisition_queue.

    This is the core integration: Lidarr discovers, Oracle acquires.

    Args:
        limit: Max wanted albums to process.
        dry_run: If True, don't actually insert -- just count.

    Returns:
        Stats dict: {albums_checked, tracks_found, inserted, skipped, errors}.
    """
    from oracle.db.schema import get_connection, get_write_mode

    stats = {
        "albums_checked": 0,
        "tracks_found": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
    }

    if not dry_run and get_write_mode() != "apply_allowed":
        logger.error("[LIDARR] Write mode not allowed -- set LYRA_WRITE_MODE=apply_allowed")
        return stats

    wanted = get_wanted(limit=limit)
    if not wanted:
        logger.info("[LIDARR] No wanted albums found.")
        return stats

    conn = get_connection(timeout=10.0) if not dry_run else None
    cursor = conn.cursor() if conn else None

    for album in wanted:
        stats["albums_checked"] += 1
        album_id = album.get("id")
        album_title = album.get("title", "Unknown Album")
        artist_info = album.get("artist", {})
        artist_name = artist_info.get("artistName", "Unknown")

        try:
            tracks = get_album_tracks(album_id)
        except Exception as exc:
            logger.warning("[LIDARR] Failed to get tracks for album %s: %s", album_title, exc)
            stats["errors"] += 1
            continue

        for track in tracks:
            stats["tracks_found"] += 1
            track_title = track.get("title", "").strip()
            if not track_title:
                stats["skipped"] += 1
                continue

            if dry_run:
                logger.info("  [DRY] Would insert: %s - %s (%s)", artist_name, track_title, album_title)
                stats["inserted"] += 1
                continue

            # Check if already in queue
            cursor.execute(
                "SELECT 1 FROM acquisition_queue WHERE LOWER(artist) = LOWER(?) AND LOWER(title) = LOWER(?) LIMIT 1",
                (artist_name, track_title),
            )
            if cursor.fetchone():
                stats["skipped"] += 1
                continue

            # Insert into acquisition_queue
            try:
                cursor.execute(
                    """
                    INSERT INTO acquisition_queue (artist, title, album, source, status, priority_score, added_at)
                    VALUES (?, ?, ?, 'lidarr', 'pending', 3.0, datetime('now'))
                    """,
                    (artist_name, track_title, album_title),
                )
                stats["inserted"] += 1
            except Exception as exc:
                logger.debug("[LIDARR] Insert failed for %s - %s: %s", artist_name, track_title, exc)
                stats["errors"] += 1

    if conn:
        conn.commit()
        conn.close()

    logger.info(
        "[LIDARR] Sync complete: albums=%d tracks=%d inserted=%d skipped=%d errors=%d",
        stats["albums_checked"],
        stats["tracks_found"],
        stats["inserted"],
        stats["skipped"],
        stats["errors"],
    )
    return stats
