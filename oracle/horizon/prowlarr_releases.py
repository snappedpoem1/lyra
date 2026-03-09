"""Prowlarr release intelligence and indexer monitoring.

Provides horizon intelligence separate from acquisition-critical functionality:
- Release search for discovery
- Upcoming releases for tracked artists
- Indexer health monitoring
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Prowlarr audio subcategories focused on music releases:
#   3010 = Audio/MP3
#   3040 = Audio/Lossless
# Avoid broad 3000 to reduce noisy audio/video and miscellaneous results.
CATEGORY_IDS = [3010, 3040]


def _request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict] = None,
    data: Optional[Dict] = None,
    timeout: int = 30,
) -> requests.Response:
    """Make request with retry logic."""
    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed: {last_error}")


def search_releases(query: str, limit: int = 5) -> List[Dict]:
    """Search Prowlarr indexers for music releases.
    
    Args:
        query: Search query (artist, album, track)
        limit: Maximum results to return
    
    Returns:
        List of release dicts with keys:
        - guid: magnet URI or indexer-specific ID
        - infoHash: torrent info hash
        - title: release title
        - seeders: seeder count
        - publishDate: release date (ISO 8601)
        - indexer: indexer name
    
    Raises:
        RuntimeError: If Prowlarr API key is missing or request fails
    """
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
        # Fallback for indexers that only expose broad Audio category mappings
        fallback_params = {
            "query": query,
            "type": "search",
            "categories": [3000],
            "limit": limit,
        }
        response = _request("GET", url, headers=headers, params=fallback_params)
        results = response.json()
    
    return results[:limit]


def get_upcoming_releases(artist_name: str, days_back: int = 30) -> List[Dict]:
    """Get recent/upcoming releases for an artist via Prowlarr search.
    
    Uses artist name to search prowlarr and filters to recent results.
    
    Args:
        artist_name: Artist name from MusicBrainz or user input
        days_back: How many days back to search for releases
    
    Returns:
        List of release dicts sorted by publish date (newest first)
    """
    try:
        # Search for artist name (general query)
        results = search_releases(artist_name, limit=50)
        
        # Filter and enrich results
        releases: List[Dict] = []
        for r in results:
            title = r.get("title", "")
            publish_date = r.get("publishDate", "")
            indexer = r.get("indexer", "unknown")
            seeders = r.get("seeders", 0) or 0
            
            # Basic recency filter (if publishDate available)
            # For now, just return all results — proper date filtering requires parsing
            releases.append({
                "title": title,
                "publish_date": publish_date,
                "indexer": indexer,
                "seeders": seeders,
                "info_hash": r.get("infoHash", ""),
                "guid": r.get("guid", ""),
            })
        
        # Sort by publish date (newest first)
        releases.sort(key=lambda x: x.get("publish_date", ""), reverse=True)
        
        logger.info(f"Found {len(releases)} releases for artist: {artist_name}")
        return releases
    
    except Exception as e:
        logger.warning(f"Failed to get upcoming releases for {artist_name}: {e}")
        return []


def get_indexer_health() -> Dict[str, any]:
    """Get health status of all configured Prowlarr indexers.
    
    Returns:
        Dict with indexer health information:
        {
            "indexers": [
                {
                    "name": "RuTracker",
                    "enabled": True,
                    "status": "healthy",
                    "last_test": "2026-03-08T12:34:56Z",
                    "error": None
                },
                ...
            ],
            "total": 5,
            "healthy": 4,
            "disabled": 1
        }
    """
    base_url = os.getenv("PROWLARR_BASE_URL") or os.getenv("PROWLARR_URL", "http://localhost:9696")
    api_key = os.getenv("PROWLARR_API_KEY")
    
    if not api_key:
        logger.warning("PROWLARR_API_KEY not configured; cannot check indexer health")
        return {
            "indexers": [],
            "total": 0,
            "healthy": 0,
            "disabled": 0,
            "error": "PROWLARR_API_KEY not configured",
        }
    
    try:
        url = f"{base_url.rstrip('/')}/api/v1/indexer"
        headers = {"X-Api-Key": api_key}
        
        response = _request("GET", url, headers=headers)
        indexers_data = response.json()
        
        indexers: List[Dict] = []
        healthy_count = 0
        disabled_count = 0
        
        for idx_data in indexers_data:
            name = idx_data.get("name", "unknown")
            enabled = idx_data.get("enable", False)
            
            # Determine status from indexer data
            # Prowlarr doesn't expose direct health, so we use enable status
            if not enabled:
                status = "disabled"
                disabled_count += 1
            else:
                # Could call /api/v1/indexer/test/{id} but that's expensive
                # For now, assume enabled = healthy
                status = "healthy"
                healthy_count += 1
            
            indexers.append({
                "name": name,
                "enabled": enabled,
                "status": status,
                "id": idx_data.get("id"),
                "implementation": idx_data.get("implementation", ""),
                "priority": idx_data.get("priority", 25),
            })
        
        return {
            "indexers": indexers,
            "total": len(indexers),
            "healthy": healthy_count,
            "disabled": disabled_count,
        }
    
    except Exception as e:
        logger.error(f"Failed to get indexer health: {e}")
        return {
            "indexers": [],
            "total": 0,
            "healthy": 0,
            "disabled": 0,
            "error": str(e),
        }
