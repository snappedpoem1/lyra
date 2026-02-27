"""
The Alchemist - Cross-Genre Discovery Engine

Translates abstract vibes into concrete acquisition targets.
Identifies "Bridge Artists" who span multiple genres.

Features:
- Cross-genre fusion hunting (Punk + EDM â†’ The Prodigy)
- Discogs API integration for release discovery
- Automatic tagging (fusion:punk_electronic, context:bridge)
- Remix/mashup preference filtering

Author: Lyra Oracle v9.0
"""

import os
import logging
import requests
from typing import Optional, List, Dict

from oracle.config import get_connection
from oracle.enrichers.cache import make_lookup_key, get_or_set_payload

logger = logging.getLogger(__name__)

# Discogs API Configuration
DISCOGS_API_TOKEN = os.getenv("DISCOGS_API_TOKEN", "") or os.getenv("DISCOGS_TOKEN", "")
DISCOGS_BASE_URL = "https://api.discogs.com"
DISCOGS_CACHE_TTL_SECONDS = int(os.getenv("LYRA_CACHE_TTL_DISCOGS_SECONDS", "1209600") or "1209600")


class Scout:
    """The Alchemist - Translates vibes into targets."""
    
    def __init__(self):
        self.conn = get_connection()
        self.session = requests.Session()
        if DISCOGS_API_TOKEN:
            self.session.headers.update({
                "Authorization": f"Discogs token={DISCOGS_API_TOKEN}",
                "User-Agent": "LyraOracle/9.0"
            })
    
    def cross_genre_hunt(
        self,
        source_genre: str,
        target_genre: str,
        limit: int = 20,
        prefer_remixes: bool = True
    ) -> List[Dict]:
        """
        Hunt for bridge artists spanning two genres.
        
        Args:
            source_genre: Starting genre (e.g., "Punk")
            target_genre: Target genre (e.g., "Electronic")
            limit: Max results
            prefer_remixes: Prioritize remix releases
        
        Returns:
            List of targets with download metadata
        """
        logger.info(f"ðŸ”¬ SCOUT: Tracing fusion [{source_genre}] Ã— [{target_genre}]")
        
        # Phase 1: Identify bridge artists
        bridge_artists = self._find_bridge_artists(source_genre, target_genre)
        logger.info(f"  â†’ {len(bridge_artists)} bridge artists identified")
        
        # Phase 2: Filter for remix releases
        targets = []
        for artist in bridge_artists[:limit]:
            releases = self._get_artist_releases(
                artist["name"],
                style_filter=[source_genre, target_genre],
                format_filter="Remix" if prefer_remixes else None
            )
            
            for release in releases:
                targets.append({
                    "artist": artist["name"],
                    "title": release["title"],
                    "year": release.get("year"),
                    "genres": release.get("genres", []),
                    "styles": release.get("styles", []),
                    "format": release.get("format"),
                    "discogs_url": release.get("url"),
                    "tags": [
                        f"fusion:{source_genre.lower()}_{target_genre.lower()}",
                        "context:bridge",
                        "scout:cross_genre"
                    ],
                    "acquisition_priority": self._calculate_priority(release, source_genre, target_genre)
                })
        
        # Sort by priority
        targets.sort(key=lambda x: x["acquisition_priority"], reverse=True)
        
        logger.info(f"  â†’ {len(targets)} targets locked")
        return targets[:limit]
    
    def _find_bridge_artists(self, genre1: str, genre2: str) -> List[Dict]:
        """
        Query Discogs for artists tagged with both genres.
        """
        # Try direct database search first
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT artist
            FROM tracks
            WHERE genre LIKE ? OR genre LIKE ?
            GROUP BY artist
            HAVING COUNT(DISTINCT genre) > 1
        """, (f"%{genre1}%", f"%{genre2}%"))
        
        local_artists = [{"name": row[0], "source": "local"} for row in cursor.fetchall()]
        
        if local_artists:
            logger.info(f"  â†’ Found {len(local_artists)} bridge artists in local library")
            return local_artists
        # Fallback: Query Discogs API
        if not DISCOGS_API_TOKEN:
            logger.warning("  No Discogs token. Limited to local library.")
            return []

        lookup_key = make_lookup_key("scout_bridge_artists", genre1, genre2)

        def _fetch() -> Dict:
            try:
                response = self.session.get(
                    f"{DISCOGS_BASE_URL}/database/search",
                    params={
                        "type": "artist",
                        "style": f"{genre1},{genre2}",
                        "per_page": 50,
                    },
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"Discogs API error: {response.status_code}")
                    return {"_miss": True}
                data = response.json()
                return {"results": data.get("results", [])}
            except Exception as e:
                logger.error(f"Discogs search failed: {e}")
                return {"_miss": True}

        payload = get_or_set_payload(
            provider="scout_discogs",
            lookup_key=lookup_key,
            max_age_seconds=DISCOGS_CACHE_TTL_SECONDS,
            fetcher=_fetch,
            miss_payload={"_miss": True},
        )
        if payload.get("_miss"):
            return []

        artists = [
            {"name": result.get("title"), "source": "discogs", "id": result.get("id")}
            for result in payload.get("results", [])
            if result.get("title")
        ]
        logger.info(f"  Found {len(artists)} bridge artists from Discogs")
        return artists

    def _get_artist_releases(
        self,
        artist_name: str,
        style_filter: Optional[List[str]] = None,
        format_filter: Optional[str] = None
    ) -> List[Dict]:
        """Get releases for an artist with optional filters."""
        if not DISCOGS_API_TOKEN:
            return []
        
        try:
            # Search for artist
            response = self.session.get(
                f"{DISCOGS_BASE_URL}/database/search",
                params={"type": "artist", "q": artist_name, "per_page": 1},
                timeout=10
            )
            
            if response.status_code != 200 or not response.json().get("results"):
                return []
            
            artist_id = response.json()["results"][0]["id"]
            
            # Get artist releases
            response = self.session.get(
                f"{DISCOGS_BASE_URL}/artists/{artist_id}/releases",
                params={"per_page": 50, "sort": "year", "sort_order": "desc"},
                timeout=10
            )
            
            if response.status_code != 200:
                return []
            
            releases = response.json().get("releases", [])
            
            # Apply filters
            if style_filter:
                releases = [
                    r for r in releases
                    if any(style in str(r.get("style", "")) for style in style_filter)
                ]
            
            if format_filter:
                releases = [
                    r for r in releases
                    if format_filter.lower() in str(r.get("format", "")).lower()
                ]
            
            return releases
        
        except Exception as e:
            logger.error(f"  âœ— Failed to get releases for {artist_name}: {e}")
            return []
    
    def _calculate_priority(self, release: Dict, genre1: str, genre2: str) -> float:
        """
        Calculate acquisition priority based on release metadata.
        
        Scoring:
        - Remix/EP: +0.3
        - Recent (2010+): +0.2
        - Both genres present: +0.3
        - Well-rated: +0.2
        """
        score = 0.5  # Base score
        
        # Prefer remixes and EPs
        format_str = str(release.get("format", "")).lower()
        if "remix" in format_str or "ep" in format_str:
            score += 0.3
        
        # Prefer recent releases
        year = release.get("year", 0)
        if year >= 2010:
            score += 0.2
        elif year >= 2000:
            score += 0.1
        
        # Check genre overlap
        styles = [s.lower() for s in release.get("styles", [])]
        if genre1.lower() in styles and genre2.lower() in styles:
            score += 0.3
        
        return min(score, 1.0)
    
    def discover_by_mood(self, mood: str, limit: int = 10) -> List[Dict]:
        """
        Semantic mood-based discovery.
        
        Maps abstract moods to concrete musical characteristics, then searches.
        
        Example moods:
        - "aggressive rebellion" â†’ Punk, Hardcore, Industrial
        - "euphoric escape" â†’ Trance, Progressive House
        - "melancholic introspection" â†’ Post-Rock, Ambient, Shoegaze
        """
        logger.info(f"ðŸ’­ SCOUT: Decoding mood [{mood}]")
        
        # Mood â†’ Genre mapping (can be enhanced with LLM)
        mood_map = {
            "aggressive": ["Punk", "Hardcore", "Metal", "Industrial"],
            "euphoric": ["Trance", "Progressive House", "Uplifting"],
            "melancholic": ["Post-Rock", "Ambient", "Shoegaze", "Slowcore"],
            "energetic": ["Drum and Bass", "Breakcore", "Techno"],
            "dark": ["Darkwave", "EBM", "Dark Ambient", "Witch House"],
            "rebellious": ["Punk", "Garage Rock", "Grunge"],
            "introspective": ["Indie Folk", "Singer-Songwriter", "Chamber Pop"]
        }
        
        # Find matching genres
        mood_lower = mood.lower()
        genres = []
        for key, genre_list in mood_map.items():
            if key in mood_lower:
                genres.extend(genre_list)
        
        if not genres:
            logger.warning(f"  âš ï¸  Mood '{mood}' not mapped. Using literal search.")
            genres = [mood]
        
        logger.info(f"  â†’ Mapped to genres: {genres}")
        
        # Search local library first
        cursor = self.conn.cursor()
        placeholders = " OR ".join(["genre LIKE ?" for _ in genres])
        params = [f"%{g}%" for g in genres]
        
        cursor.execute("""
            SELECT track_id, artist, title, genre, filepath
            FROM tracks
            WHERE {placeholders}
            ORDER BY RANDOM()
            LIMIT ?
        """, params + [limit])
        
        results = [
            {
                "track_id": row[0],
                "artist": row[1],
                "title": row[2],
                "genre": row[3],
                "filepath": row[4],
                "file_path": row[4],  # Back-compat alias for legacy clients
                "source": "local"
            }
            for row in cursor.fetchall()
        ]
        
        logger.info(f"  â†’ {len(results)} local matches found")
        return results


# Singleton instance
scout = Scout()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 3:
        print("\nðŸ”¬ Lyra Scout - Cross-Genre Discovery\n")
        print("Usage:")
        print("  python -m oracle.scout <genre1> <genre2> [limit]")
        print("\nExample:")
        print("  python -m oracle.scout Punk Electronic 20")
        print("  python -m oracle.scout \"Hip Hop\" Jazz 15\n")
        sys.exit(0)
    
    genre1 = sys.argv[1]
    genre2 = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    
    targets = scout.cross_genre_hunt(genre1, genre2, limit)
    
    print(f"\nðŸŽ¯ TARGETS LOCKED: {len(targets)}\n")
    for i, target in enumerate(targets, 1):
        print(f"{i:2}. [{target['acquisition_priority']:.2f}] {target['artist']} - {target['title']}")
        print(f"    Genres: {', '.join(target.get('genres', []))}")
        print(f"    Tags: {', '.join(target['tags'])}")
        if target.get('discogs_url'):
            print(f"    URL: {target['discogs_url']}")
        print()


