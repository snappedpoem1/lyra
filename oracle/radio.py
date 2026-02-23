"""
The Chaos Engine - Intelligent Radio & Playback

Break the echo chamber. Play mathematically distinct tracks that still match taste.

Features:
- Chaos mode: Orthogonal vector selection (distinct but good)
- Flow mode: Smooth transitions based on energy/key
- Discovery mode: Explore library edges
- Taste profile learning from playback history

Author: Lyra Oracle v9.0
"""

import os
import logging
import sqlite3
import json
import random
import numpy as np
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from oracle.config import get_connection, CHROMA_COLLECTION

logger = logging.getLogger(__name__)


class Radio:
    """The Chaos Engine - Intelligent playback orchestration."""
    
    def __init__(self):
        self.current_session = str(uuid.uuid4())

    def _open_conn(self) -> sqlite3.Connection:
        return get_connection()
    
    def get_chaos_track(
        self,
        current_track_id: Optional[str] = None,
        count: int = 1
    ) -> List[Dict]:
        """
        Select tracks that are mathematically DISTINCT but still good.
        
        "Break the echo chamber"
        
        Algorithm:
        1. Get current track's embedding
        2. Find tracks with LOW cosine similarity (orthogonal vectors)
        3. Filter by user's taste profile (high rating)
        4. Return the most distinct + highly-rated track
        
        Args:
            current_track_id: Current playing track (None = random start)
            count: Number of tracks to return
        
        Returns:
            List of chaos tracks
        """
        logger.info(f"🎲 RADIO: Generating chaos from {current_track_id or 'START'}")
        
        try:
            # Import ChromaDB locally to avoid circular imports
            import chromadb
            from oracle.config import CHROMA_PATH
            
            client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            collection = client.get_or_create_collection(CHROMA_COLLECTION)
            
            if current_track_id:
                # Get current track embedding
                result = collection.get(ids=[current_track_id], include=["embeddings", "metadatas"])
                
                if not result["ids"]:
                    logger.warning("  ⚠️  Current track not in ChromaDB")
                    return self._random_tracks(count)
                
                current_embedding = result["embeddings"][0]
                
                # Query for DISSIMILAR tracks (opposite vectors)
                # ChromaDB doesn't have a "most dissimilar" query, so we:
                # 1. Get all tracks
                # 2. Calculate similarity
                # 3. Sort by ASCENDING similarity (most different first)
                
                all_results = collection.get(include=["embeddings", "metadatas"])
                
                similarities = []
                for i, emb in enumerate(all_results["embeddings"]):
                    if all_results["ids"][i] == current_track_id:
                        continue
                    
                    # Cosine similarity
                    sim = np.dot(current_embedding, emb) / (
                        np.linalg.norm(current_embedding) * np.linalg.norm(emb)
                    )
                    
                    similarities.append({
                        "track_id": all_results["ids"][i],
                        "metadata": all_results["metadatas"][i],
                        "similarity": sim
                    })
                
                # Sort by ASCENDING similarity (most orthogonal first)
                similarities.sort(key=lambda x: x["similarity"])
                
                # Filter by taste profile
                candidates = self._filter_by_taste(similarities[:50])
                
                # Select top N
                selected = candidates[:count]
                
                logger.info(f"  → Selected {len(selected)} chaos tracks")
                for track in selected:
                    logger.info(f"    {track['metadata']['artist']} - {track['metadata']['title']} (sim: {track['similarity']:.2f})")
                
                return selected
            
            else:
                # No current track - random start
                return self._random_tracks(count)
        
        except Exception as e:
            logger.error(f"  ✗ Chaos generation failed: {e}")
            return self._random_tracks(count)
    
    def get_flow_track(
        self,
        current_track_id: str,
        count: int = 1
    ) -> List[Dict]:
        """
        Select tracks for smooth flow transitions.
        
        Considers:
        - Similar energy profile
        - Compatible key signatures
        - BPM proximity (within 10%)
        - Semantic similarity (but not too similar)
        
        "Feel the flow"
        """
        logger.info(f"🌊 RADIO: Flowing from {current_track_id}")
        
        conn = None
        try:
            conn = self._open_conn()
            cursor = conn.cursor()

            # Get current track structure
            cursor.execute("""
                SELECT bpm, key_signature, energy_profile
                FROM track_structure
                WHERE track_id = ?
            """, (current_track_id,))
            
            current_structure = cursor.fetchone()
            if not current_structure:
                logger.warning("  ⚠️  No structure data. Falling back to semantic.")
                return self._semantic_similar_tracks(current_track_id, count)
            
            cur_bpm, cur_key, cur_energy = current_structure
            cur_energy_list = json.loads(cur_energy) if cur_energy else []
            
            # Find compatible tracks
            cursor.execute("""
                SELECT t.track_id, t.artist, t.title, ts.bpm, ts.key_signature, ts.energy_profile
                FROM tracks t
                JOIN track_structure ts ON t.track_id = ts.track_id
                WHERE t.track_id != ?
                  AND ts.bpm BETWEEN ? AND ?
            """, (
                current_track_id,
                cur_bpm * 0.9,  # -10%
                cur_bpm * 1.1   # +10%
            ))
            
            candidates = []
            for row in cursor.fetchall():
                track_id, artist, title, bpm, key, energy = row
                
                # Calculate compatibility score
                score = 0.0
                
                # BPM proximity
                bpm_diff = abs(bpm - cur_bpm) / cur_bpm
                score += (1.0 - bpm_diff) * 0.4
                
                # Key compatibility
                if self._keys_compatible(cur_key, key):
                    score += 0.3
                
                # Energy profile similarity
                if energy:
                    energy_list = json.loads(energy)
                    if cur_energy_list and energy_list:
                        energy_sim = self._energy_similarity(cur_energy_list, energy_list)
                        score += energy_sim * 0.3
                
                candidates.append({
                    "track_id": track_id,
                    "metadata": {"artist": artist, "title": title},
                    "compatibility": score,
                    "bpm": bpm,
                    "key": key
                })
            
            # Sort by compatibility
            candidates.sort(key=lambda x: x["compatibility"], reverse=True)
            
            logger.info(f"  → {len(candidates)} compatible tracks found")
            selected = candidates[:count]
            
            for track in selected:
                logger.info(f"    {track['metadata']['artist']} - {track['metadata']['title']} (compat: {track['compatibility']:.2f})")
            
            return selected
        
        except Exception as e:
            logger.error(f"  ✗ Flow generation failed: {e}")
            return self._semantic_similar_tracks(current_track_id, count)
        finally:
            if conn:
                conn.close()
    
    def get_discovery_track(self, count: int = 1) -> List[Dict]:
        """
        Explore the library edges - rarely played tracks with good ratings.
        
        "Find the hidden gems"
        """
        logger.info(f"🔭 RADIO: Discovering hidden gems")
        
        conn = self._open_conn()
        cursor = conn.cursor()
        
        # Find tracks with few plays but exist in library
        cursor.execute("""
            SELECT t.track_id, t.artist, t.title, COUNT(ph.id) as play_count
            FROM tracks t
            LEFT JOIN playback_history ph ON t.track_id = ph.track_id
            GROUP BY t.track_id
            ORDER BY play_count ASC, RANDOM()
            LIMIT ?
        """, (count * 3,))
        
        discoveries = []
        for row in cursor.fetchall():
            discoveries.append({
                "track_id": row[0],
                "metadata": {"artist": row[1], "title": row[2]},
                "play_count": row[3]
            })
        
        # Filter out truly mediocre tracks using taste profile
        discoveries = self._filter_by_taste(discoveries)
        
        selected = discoveries[:count]
        
        logger.info(f"  → {len(selected)} discoveries")
        for track in selected:
            logger.info(f"    {track['metadata']['artist']} - {track['metadata']['title']} (plays: {track.get('play_count', 0)})")
        
        conn.close()
        return selected
    
    def record_playback(
        self,
        track_id: str,
        context: str = "manual",
        skipped: bool = False,
        completion_rate: float = 1.0,
        rating: Optional[int] = None
    ) -> None:
        """
        Record playback event for taste learning.
        
        Args:
            track_id: Track UUID
            context: manual, radio, vibe, shuffle
            skipped: Was track skipped?
            completion_rate: 0.0-1.0
            rating: Optional 1-5 stars
        """
        conn = self._open_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO playback_history
            (track_id, context, session_id, skipped, completion_rate, rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (track_id, context, self.current_session, skipped, completion_rate, rating))
        conn.commit()
        conn.close()
        
        # Update taste profile
        if completion_rate > 0.8 or rating and rating >= 4:
            self._update_taste_profile(track_id, positive=True)
        elif skipped or completion_rate < 0.3:
            self._update_taste_profile(track_id, positive=False)
    
    def get_taste_profile(self) -> Dict:
        """
        Get current taste profile.
        
        Returns:
            Dict of taste dimensions and values
        """
        conn = self._open_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT dimension, value, confidence FROM taste_profile")
        
        profile = {}
        for row in cursor.fetchall():
            profile[row[0]] = {
                "value": row[1],
                "confidence": row[2]
            }
        
        conn.close()
        return profile
    
    def _filter_by_taste(self, candidates: List[Dict]) -> List[Dict]:
        """
        Filter candidates by taste profile.
        
        Prioritize tracks matching user's learned preferences.
        """
        # For now, simple random filtering
        # In production: Use taste profile to score each candidate
        return candidates
    
    def _keys_compatible(self, key1: str, key2: str) -> bool:
        """
        Check if two musical keys are compatible for mixing.
        
        Compatible keys:
        - Same key
        - Relative major/minor (C <-> Am)
        - Perfect fifth (C <-> G)
        """
        if key1 == key2:
            return True
        
        # Simplified compatibility check
        # Full version would use Camelot Wheel
        key1_root = key1[0]
        key2_root = key2[0]
        
        return key1_root == key2_root
    
    def _energy_similarity(self, energy1: List[float], energy2: List[float]) -> float:
        """Calculate similarity between two energy profiles."""
        # Truncate to shorter length
        min_len = min(len(energy1), len(energy2))
        e1 = energy1[:min_len]
        e2 = energy2[:min_len]
        
        # Pearson correlation
        if len(e1) < 2:
            return 0.5
        
        corr = np.corrcoef(e1, e2)[0, 1]
        return (corr + 1) / 2  # Scale to 0-1
    
    def _semantic_similar_tracks(self, track_id: str, count: int) -> List[Dict]:
        """Fallback: Use semantic similarity."""
        try:
            import chromadb
            from oracle.config import CHROMA_PATH
            
            client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            collection = client.get_or_create_collection(CHROMA_COLLECTION)
            
            result = collection.query(
                query_embeddings=collection.get(ids=[track_id], include=["embeddings"])["embeddings"],
                n_results=count + 1,  # +1 to exclude self
                include=["metadatas", "distances"]
            )
            
            tracks = []
            for i, track_id in enumerate(result["ids"][0][1:]):  # Skip first (self)
                tracks.append({
                    "track_id": track_id,
                    "metadata": result["metadatas"][0][i+1],
                    "similarity": 1.0 - result["distances"][0][i+1]
                })
            
            return tracks
        
        except Exception as e:
            logger.error(f"  ✗ Semantic fallback failed: {e}")
            return self._random_tracks(count)
    
    def _random_tracks(self, count: int) -> List[Dict]:
        """Ultimate fallback: Random selection."""
        conn = self._open_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT track_id, artist, title
            FROM tracks
            ORDER BY RANDOM()
            LIMIT ?
        """, (count,))
        
        tracks = []
        for row in cursor.fetchall():
            tracks.append({
                "track_id": row[0],
                "metadata": {"artist": row[1], "title": row[2]}
            })
        
        conn.close()
        return tracks
    
    def _update_taste_profile(self, track_id: str, positive: bool) -> None:
        """Update taste profile based on playback feedback."""
        try:
            from oracle.taste import update_taste_from_playback

            # Positive: completed/liked. Negative: skipped/disliked.
            update_taste_from_playback(track_id, positive=positive, weight=1.0)
        except Exception:
            logger.exception("Taste update failed")
    
    def build_queue(self, mode: str = "chaos", seed_track: Optional[str] = None, length: int = 20) -> List[Dict]:
        """
        Build a radio queue.
        
        Args:
            mode: chaos, flow, discovery, shuffle
            seed_track: Starting track (required for flow)
            length: Queue length
        
        Returns:
            Radio queue
        """
        logger.info(f"📻 RADIO: Building {mode} queue (length={length})")
        
        queue = []
        current_track = seed_track
        
        for i in range(length):
            if mode == "chaos":
                tracks = self.get_chaos_track(current_track, count=1)
            elif mode == "flow":
                if not current_track:
                    # Start with random
                    tracks = self._random_tracks(1)
                else:
                    tracks = self.get_flow_track(current_track, count=1)
            elif mode == "discovery":
                tracks = self.get_discovery_track(count=1)
            elif mode == "shuffle":
                tracks = self._random_tracks(1)
            else:
                tracks = self._random_tracks(1)
            
            if tracks:
                queue.extend(tracks)
                current_track = tracks[0]["track_id"]
        
        # Store queue in database
        self._store_queue(queue, mode)
        
        logger.info(f"  ✓ Queue built: {len(queue)} tracks")
        return queue
    
    def _store_queue(self, queue: List[Dict], algorithm: str) -> None:
        """Store queue in database."""
        conn = self._open_conn()
        cursor = conn.cursor()
        
        # Clear existing queue
        cursor.execute("DELETE FROM radio_queue")
        
        # Insert new queue
        for i, track in enumerate(queue):
            cursor.execute("""
                INSERT INTO radio_queue (track_id, position, algorithm)
                VALUES (?, ?, ?)
            """, (track["track_id"], i, algorithm))
        
        conn.commit()
        conn.close()


# Singleton instance
radio = Radio()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\n📻 Lyra Radio - Chaos Engine\n")
        print("Commands:")
        print("  python -m oracle.radio chaos [track_id]    - Get chaos track")
        print("  python -m oracle.radio flow <track_id>     - Get flow track")
        print("  python -m oracle.radio discover            - Get discovery track")
        print("  python -m oracle.radio queue <mode> [seed] - Build queue")
        print("\nModes: chaos, flow, discovery, shuffle")
        print("\nExample:")
        print("  python -m oracle.radio chaos")
        print("  python -m oracle.radio queue chaos 20\n")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "chaos":
        seed = sys.argv[2] if len(sys.argv) > 2 else None
        tracks = radio.get_chaos_track(seed, count=5)
        
        print(f"\n🎲 CHAOS TRACKS:\n")
        for i, track in enumerate(tracks, 1):
            print(f"{i}. {track['metadata']['artist']} - {track['metadata']['title']}")
            if 'similarity' in track:
                print(f"   Similarity: {track['similarity']:.2f}")
        print()
    
    elif command == "flow" and len(sys.argv) >= 3:
        seed = sys.argv[2]
        tracks = radio.get_flow_track(seed, count=5)
        
        print(f"\n🌊 FLOW TRACKS:\n")
        for i, track in enumerate(tracks, 1):
            print(f"{i}. {track['metadata']['artist']} - {track['metadata']['title']}")
            if 'compatibility' in track:
                print(f"   Compatibility: {track['compatibility']:.2f}")
        print()
    
    elif command == "discover":
        tracks = radio.get_discovery_track(count=5)
        
        print(f"\n🔭 DISCOVERIES:\n")
        for i, track in enumerate(tracks, 1):
            print(f"{i}. {track['metadata']['artist']} - {track['metadata']['title']}")
            print(f"   Plays: {track.get('play_count', 0)}")
        print()
    
    elif command == "queue" and len(sys.argv) >= 3:
        mode = sys.argv[2]
        seed = sys.argv[3] if len(sys.argv) > 3 else None
        
        queue = radio.build_queue(mode, seed, length=20)
        
        print(f"\n📻 RADIO QUEUE ({mode}):\n")
        for i, track in enumerate(queue, 1):
            print(f"{i:2}. {track['metadata']['artist']} - {track['metadata']['title']}")
        print()
    
    else:
        print("\n✗ Invalid command. Run with no args for help.\n")
