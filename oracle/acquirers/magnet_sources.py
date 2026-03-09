"""Magnet URI aggregation from multiple sources.

Provides a unified interface for discovering magnet URIs from:
- Prowlarr indexer search (primary)
- Manual magnet input (future)
- DHT search (future)

Normalizes results and applies source-based priority sorting.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_magnets_for_track(
    artist: str,
    title: str,
    album: Optional[str] = None,
) -> List[Dict]:
    """Aggregate magnet URIs from all available sources.
    
    Args:
        artist: Artist name
        title: Track title
        album: Album name (optional, improves search quality)
    
    Returns:
        List of magnet dicts sorted by priority:
        [
            {
                "magnet": "magnet:?xt=urn:btih:...",
                "title": "Artist - Album - Track (FLAC)",
                "seeders": 42,
                "is_flac": True,
                "source": "prowlarr"
            },
            ...
        ]
        
        Sorting priority:
        1. Prowlarr magnets with >10 seeders (boosted)
        2. FLAC quality
        3. Seeder count descending
    """
    magnets: List[Dict] = []
    
    # Source 1: Prowlarr indexer search
    prowlarr_magnets = _get_prowlarr_magnets(artist, title, album)
    magnets.extend(prowlarr_magnets)
    
    # Future: Source 2: Manual magnet input (if provided via queue)
    # Future: Source 3: DHT search
    
    if not magnets:
        logger.debug(f"No magnets found for {artist} - {title}")
        return []
    
    # Apply source-based priority sorting
    def sort_key(m: Dict) -> tuple:
        """Sort key: prowlarr boost, FLAC, seeders."""
        is_prowlarr = m.get("source") == "prowlarr"
        seeders = m.get("seeders", 0)
        is_flac = m.get("is_flac", False)
        
        # Boost prowlarr magnets with >10 seeders
        prowlarr_boost = is_prowlarr and seeders > 10
        
        # Return tuple for sorting: (boost, is_flac, seeders)
        # Higher values sort first, so negate booleans become 0/1
        return (
            -int(prowlarr_boost),  # Boosted prowlarr first (negative = higher priority)
            -int(is_flac),          # FLAC second
            -seeders,               # More seeders third
        )
    
    magnets.sort(key=sort_key)
    
    logger.info(
        f"Found {len(magnets)} magnets for {artist} - {title} "
        f"(prowlarr={len(prowlarr_magnets)})"
    )
    
    return magnets


def _get_prowlarr_magnets(
    artist: str,
    title: str,
    album: Optional[str] = None,
) -> List[Dict]:
    """Get magnets from Prowlarr indexer search.
    
    Returns empty list if Prowlarr is unavailable or search fails.
    """
    prowlarr_url = os.getenv("PROWLARR_URL", "http://localhost:9696")
    api_key = os.getenv("PROWLARR_API_KEY", "")
    
    if not api_key:
        logger.debug("Prowlarr API key not configured; skipping prowlarr source")
        return []
    
    try:
        # Import prowlarr search function from horizon module
        from oracle.horizon.prowlarr_releases import search_releases
        
        # Build search query (prefer FLAC)
        query = f"{artist} {album or title} FLAC"
        logger.debug(f"[Prowlarr] Searching: {query}")
        
        results = search_releases(query, limit=10)
        
        if not results:
            # Fallback without FLAC filter
            query = f"{artist} {title}"
            logger.debug(f"[Prowlarr] Retrying without FLAC: {query}")
            results = search_releases(query, limit=10)
        
        # Normalize prowlarr results to magnet dicts
        magnets: List[Dict] = []
        
        for r in results:
            # Extract magnet URI from prowlarr result
            # Prowlarr field map:
            #   guid = actual magnet URI for some indexers
            #   infoHash = raw hex hash (most reliable)
            #   magnetUrl = prowlarr proxy URL (do NOT use)
            
            info_hash = (r.get("infoHash") or "").strip().lower()
            magnet_uri = ""
            
            guid = (r.get("guid") or "").strip()
            if guid.lower().startswith("magnet:"):
                magnet_uri = guid
            elif info_hash:
                # Construct magnet from info hash
                dn = (r.get("title") or "").replace(" ", "+")
                magnet_uri = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"
            
            if not magnet_uri:
                continue
            
            title_str = r.get("title", "")
            seeders = r.get("seeders", 0) or 0
            is_flac = "flac" in title_str.lower()
            
            magnets.append({
                "magnet": magnet_uri,
                "title": title_str,
                "seeders": seeders,
                "is_flac": is_flac,
                "source": "prowlarr",
            })
        
        logger.debug(f"[Prowlarr] Found {len(magnets)} usable magnets")
        return magnets
    
    except ImportError:
        logger.debug("Prowlarr search module not available; skipping prowlarr source")
        return []
    except Exception as e:
        logger.warning(f"Prowlarr search failed: {e}")
        return []
