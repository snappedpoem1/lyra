"""
The Historian - Artist Lineage & Rivalry Mapper

Maps the invisible bloodlines of music:
- Band member histories (Skrillex → From First to Last)
- Collaboration networks
- Historical rivalries (Nas vs. Jay-Z)
- Influence chains (Beatles → Oasis)

Uses MusicBrainz relationships + optional LLM for rivalry detection.

Author: Lyra Oracle v9.0
"""

import os
import logging
import requests
import sqlite3
import time
import json
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from oracle.config import get_connection

logger = logging.getLogger(__name__)

# MusicBrainz API Configuration
MB_BASE_URL = "https://musicbrainz.org/ws/2"
MB_RATE_LIMIT = 1.0  # 1 request per second


class Lore:
    """The Historian - Maps artist relationships and rivalries."""
    
    def __init__(self):
        self.last_mb_request = 0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LyraOracle/9.0 (github.com/lyra-oracle)"
        })
    
    def _open_conn(self):
        """Get a fresh connection (thread-safe)."""
        return get_connection()
    
    def trace_lineage(self, artist_name: str, depth: int = 2) -> Dict:
        """
        Trace artist lineage (members, collaborators, influences).
        
        Args:
            artist_name: Artist to trace
            depth: Relationship depth (1-3)
        
        Returns:
            Lineage map with connections
        """
        logger.info(f"📜 LORE: Tracing lineage for [{artist_name}]")
        
        # Get or create artist MBID
        mbid = self._get_artist_mbid(artist_name)
        if not mbid:
            logger.warning(f"  ⚠️  Artist not found in MusicBrainz")
            return {"artist": artist_name, "connections": [], "error": "not_found"}
        
        # Fetch relationships
        connections = []
        
        # Phase 1: Member relationships
        member_of = self._get_member_relationships(mbid)
        for rel in member_of:
            self._store_connection(
                artist_name,
                rel["target"],
                "member_of",
                weight=0.8,
                metadata=json.dumps(rel.get("metadata", {}))
            )
            connections.append(rel)
            logger.info(f"  → Member of: {rel['target']}")
        
        # Phase 2: Collaboration relationships
        collabs = self._get_collaboration_relationships(mbid)
        for rel in collabs:
            self._store_connection(
                artist_name,
                rel["target"],
                "collab",
                weight=0.6,
                metadata=json.dumps(rel.get("metadata", {}))
            )
            connections.append(rel)
            logger.info(f"  → Collab with: {rel['target']}")
        
        # Phase 3: Influence relationships (if available)
        influences = self._get_influence_relationships(mbid)
        for rel in influences:
            self._store_connection(
                artist_name,
                rel["target"],
                "influence",
                weight=0.4,
                metadata=json.dumps(rel.get("metadata", {}))
            )
            connections.append(rel)
            logger.info(f"  → Influenced by: {rel['target']}")
        
        # Phase 4: Rivalry detection (requires LLM or manual data)
        rivalries = self._detect_rivalries(artist_name)
        for rival in rivalries:
            self._store_connection(
                artist_name,
                rival["target"],
                "rivalry",
                weight=-0.7,
                metadata=json.dumps(rival.get("metadata", {}))
            )
            connections.append(rival)
            logger.info(f"  ⚔️  Rivalry with: {rival['target']}")
        
        logger.info(f"  → Total connections: {len(connections)}")
        
        return {
            "artist": artist_name,
            "mbid": mbid,
            "connections": connections,
            "total": len(connections),
            "traced_at": datetime.now().isoformat()
        }
    
    def get_artist_connections(self, artist_name: str) -> List[Dict]:
        """
        Get all stored connections for an artist.
        """
        conn = self._open_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT target_artist, type, weight, metadata, created_at
                FROM connections
                WHERE source_artist = ?
                ORDER BY weight DESC
            """, (artist_name,))
            
            connections = []
            for row in cursor.fetchall():
                connections.append({
                    "target": row[0],
                    "type": row[1],
                    "weight": row[2],
                    "metadata": json.loads(row[3]) if row[3] else {},
                    "created_at": row[4]
                })
            
            return connections
        finally:
            conn.close()
    
    def find_connection_path(
        self,
        artist1: str,
        artist2: str,
        max_hops: int = 3
    ) -> Optional[List[str]]:
        """
        Find shortest connection path between two artists.
        
        Uses breadth-first search on the connection graph.
        
        Returns:
            List of artists forming the path, or None if no connection
        """
        logger.info(f"🔗 LORE: Finding path [{artist1}] → [{artist2}]")
        
        if artist1 == artist2:
            return [artist1]
        
        visited = set()
        queue = [(artist1, [artist1])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current in visited:
                continue
            visited.add(current)
            
            if len(path) > max_hops:
                continue
            
            # Get connections
            connections = self.get_artist_connections(current)
            
            for conn in connections:
                target = conn["target"]
                
                if target == artist2:
                    logger.info(f"  → Path found: {' → '.join(path + [target])}")
                    return path + [target]
                
                if target not in visited:
                    queue.append((target, path + [target]))
        
        logger.info(f"  ✗ No connection found within {max_hops} hops")
        return None
    
    def _get_artist_mbid(self, artist_name: str) -> Optional[str]:
        """Search MusicBrainz for artist MBID."""
        self._rate_limit()
        
        try:
            response = self.session.get(
                f"{MB_BASE_URL}/artist",
                params={
                    "query": f"artist:{artist_name}",
                    "fmt": "json",
                    "limit": 1
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("artists"):
                    return data["artists"][0]["id"]
            
            return None
        
        except Exception as e:
            logger.error(f"  ✗ MusicBrainz search failed: {e}")
            return None
    
    def _get_member_relationships(self, mbid: str) -> List[Dict]:
        """Get band membership relationships."""
        self._rate_limit()
        
        try:
            response = self.session.get(
                f"{MB_BASE_URL}/artist/{mbid}",
                params={
                    "inc": "artist-rels",
                    "fmt": "json"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            relations = data.get("relations", [])
            
            members = []
            for rel in relations:
                if rel.get("type") in ["member of band", "founder of band"]:
                    members.append({
                        "target": rel["artist"]["name"],
                        "type": "member_of",
                        "metadata": {
                            "begin": rel.get("begin"),
                            "end": rel.get("end"),
                            "role": rel.get("type")
                        }
                    })
            
            return members
        
        except Exception as e:
            logger.error(f"  ✗ Failed to get member relationships: {e}")
            return []
    
    def _get_collaboration_relationships(self, mbid: str) -> List[Dict]:
        """Get collaboration relationships."""
        self._rate_limit()
        
        try:
            response = self.session.get(
                f"{MB_BASE_URL}/artist/{mbid}",
                params={
                    "inc": "recording-rels+work-rels",
                    "fmt": "json"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            relations = data.get("relations", [])
            
            collabs = []
            collaborators = set()
            
            for rel in relations:
                if rel.get("type") in ["collaboration", "producer", "remixer"]:
                    target_name = rel.get("artist", {}).get("name")
                    if target_name and target_name not in collaborators:
                        collaborators.add(target_name)
                        collabs.append({
                            "target": target_name,
                            "type": "collab",
                            "metadata": {
                                "role": rel.get("type")
                            }
                        })
            
            return collabs
        
        except Exception as e:
            logger.error(f"  ✗ Failed to get collaboration relationships: {e}")
            return []
    
    def _get_influence_relationships(self, mbid: str) -> List[Dict]:
        """Get influence relationships (rare in MusicBrainz)."""
        # MusicBrainz has limited influence data
        # This could be enhanced with Last.fm similar artists or LLM
        return []
    
    def _detect_rivalries(self, artist_name: str) -> List[Dict]:
        """
        Detect rivalries using known rivalry database.
        
        In production, this would:
        1. Query a curated rivalry database
        2. Use LLM to identify beefs from lyrics/interviews
        3. Use social media sentiment analysis
        
        For now, use a hardcoded dictionary of famous rivalries.
        """
        # Famous rivalries in music history
        rivalry_db = {
            "Nas": ["Jay-Z"],
            "Jay-Z": ["Nas"],
            "Biggie": ["Tupac"],
            "Tupac": ["Biggie"],
            "Oasis": ["Blur"],
            "Blur": ["Oasis"],
            "The Beatles": ["The Rolling Stones"],
            "The Rolling Stones": ["The Beatles"],
            "Metallica": ["Megadeth"],
            "Megadeth": ["Metallica"],
        }
        
        rivals = []
        if artist_name in rivalry_db:
            for rival in rivalry_db[artist_name]:
                rivals.append({
                    "target": rival,
                    "type": "rivalry",
                    "metadata": {
                        "era": "classic",
                        "verified": True
                    }
                })
        
        return rivals
    
    def _store_connection(
        self,
        source: str,
        target: str,
        conn_type: str,
        weight: float,
        metadata: str = None
    ) -> None:
        """Store connection in database."""
        conn = self._open_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO connections
                (source_artist, target_artist, type, weight, metadata, verified)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (source, target, conn_type, weight, metadata))
            conn.commit()
        except Exception as e:
            logger.error(f"  ✗ Failed to store connection: {e}")
        finally:
            conn.close()
    
    def _rate_limit(self) -> None:
        """Enforce MusicBrainz rate limit (1 req/sec)."""
        elapsed = time.time() - self.last_mb_request
        if elapsed < MB_RATE_LIMIT:
            time.sleep(MB_RATE_LIMIT - elapsed)
        self.last_mb_request = time.time()
    
    def export_graph(self, artist_name: str, output_path: str = None) -> Dict:
        """
        Export artist connection graph as JSON for visualization.
        
        Format compatible with Vis.js network graphs.
        """
        connections = self.get_artist_connections(artist_name)
        
        nodes = [{"id": artist_name, "label": artist_name, "group": "source"}]
        edges = []
        
        for conn in connections:
            # Add target node
            nodes.append({
                "id": conn["target"],
                "label": conn["target"],
                "group": conn["type"]
            })
            
            # Add edge with color based on type
            color_map = {
                "collab": "blue",
                "member_of": "green",
                "influence": "purple",
                "rivalry": "red"
            }
            
            edges.append({
                "from": artist_name,
                "to": conn["target"],
                "label": conn["type"],
                "color": color_map.get(conn["type"], "gray"),
                "width": abs(conn["weight"]) * 3,
                "dashes": conn["weight"] < 0  # Dashed lines for rivalries
            })
        
        graph = {
            "nodes": nodes,
            "edges": edges,
            "center": artist_name
        }
        
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(graph, f, indent=2)
            logger.info(f"  → Graph exported to {output_path}")
        
        return graph


# Singleton instance
lore = Lore()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\n📜 Lyra Lore - Artist Lineage Tracer\n")
        print("Usage:")
        print("  python -m oracle.lore <artist_name>")
        print("\nExample:")
        print("  python -m oracle.lore Skrillex")
        print("  python -m oracle.lore \"Nine Inch Nails\"\n")
        sys.exit(0)
    
    artist = sys.argv[1]
    
    lineage = lore.trace_lineage(artist)
    
    print(f"\n🔗 LINEAGE MAP: {lineage['artist']}\n")
    print(f"MusicBrainz ID: {lineage.get('mbid', 'N/A')}")
    print(f"Total Connections: {lineage['total']}\n")
    
    if lineage["connections"]:
        print("Connections:")
        for conn in lineage["connections"]:
            icon = {
                "collab": "🤝",
                "member_of": "🎸",
                "influence": "💡",
                "rivalry": "⚔️"
            }.get(conn["type"], "•")
            print(f"  {icon} {conn['type']:12} → {conn['target']}")
    else:
        print("No connections found.")
    
    print()
