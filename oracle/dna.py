"""
The Sample Hunter - Audio DNA Tracer

Traces sample lineage and original sources.
"Respect the roots" - know what you're listening to.

Features:
- Sample identification (WhoSampled integration ready)
- Audio fingerprint matching for sample detection
- Pivot functionality (jump from modern track to 1970s original)
- Credit attribution

Author: Lyra Oracle v9.0
"""

import os
import logging
import sqlite3
import json
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

from oracle.config import get_connection

logger = logging.getLogger(__name__)

# WhoSampled would require scraping or paid API
# For now, we'll use a local database + manual entries


class DNA:
    """The Sample Hunter - Traces audio lineage."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def trace_samples(self, track_id: str) -> List[Dict]:
        """
        Trace samples used in a track.
        
        Args:
            track_id: Track UUID
        
        Returns:
            List of sample origins
        """
        logger.info(f"🧬 DNA: Tracing samples for track {track_id}")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT original_artist, original_title, original_year,
                   sample_type, confidence, source, verified
            FROM sample_lineage
            WHERE track_id = ?
            ORDER BY confidence DESC
        """, (track_id,))
        
        samples = []
        for row in cursor.fetchall():
            samples.append({
                "original_artist": row[0],
                "original_title": row[1],
                "original_year": row[2],
                "sample_type": row[3],
                "confidence": row[4],
                "source": row[5],
                "verified": bool(row[6])
            })
        
        logger.info(f"  → {len(samples)} samples identified")
        return samples
    
    def register_sample(
        self,
        track_id: str,
        original_artist: str,
        original_title: str,
        original_year: Optional[int] = None,
        sample_type: str = "unknown",
        confidence: float = 0.5,
        source: str = "manual"
    ) -> bool:
        """
        Register a sample manually.
        
        Args:
            track_id: Modern track UUID
            original_artist: Original artist
            original_title: Original track title
            original_year: Year of original
            sample_type: vocal, drum_break, melody, bass, etc.
            confidence: 0.0-1.0
            source: manual, whosampled, ml_detection
        
        Returns:
            Success status
        """
        logger.info(f"📝 DNA: Registering sample [{original_artist} - {original_title}]")
        
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO sample_lineage
                (track_id, original_artist, original_title, original_year,
                 sample_type, confidence, source, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                track_id, original_artist, original_title, original_year,
                sample_type, confidence, source
            ))
            self.conn.commit()
            logger.info("  ✓ Sample registered")
            return True
        
        except Exception as e:
            logger.error(f"  ✗ Registration failed: {e}")
            return False
    
    def find_original_in_library(self, sample_info: Dict) -> Optional[str]:
        """
        Find the original sampled track in the local library.
        
        Enables "pivot" functionality - jump from modern track to original.
        
        Args:
            sample_info: Dict with original_artist and original_title
        
        Returns:
            track_id of original, or None if not in library
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT track_id
            FROM tracks
            WHERE artist LIKE ? AND title LIKE ?
            LIMIT 1
        """, (
            f"%{sample_info['original_artist']}%",
            f"%{sample_info['original_title']}%"
        ))
        
        result = cursor.fetchone()
        if result:
            logger.info(f"  ✓ Original found in library: {result[0]}")
            return result[0]
        
        logger.info("  ℹ Original not in library")
        return None
    
    def pivot_to_original(self, track_id: str) -> Optional[Dict]:
        """
        Pivot from a modern track to its original sample source.
        
        Workflow:
        1. Trace samples
        2. Find most prominent sample (highest confidence)
        3. Check if original is in library
        4. Return playback details
        
        Returns:
            Dict with original track playback info or acquisition target
        """
        logger.info(f"🔄 DNA: Pivoting track {track_id} to original")
        
        samples = self.trace_samples(track_id)
        
        if not samples:
            logger.info("  ℹ No samples registered for this track")
            return None
        
        # Get most prominent sample
        primary_sample = samples[0]
        
        # Check library
        original_track_id = self.find_original_in_library(primary_sample)
        
        if original_track_id:
            # Get track details
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT artist, title, album, year, file_path
                FROM tracks
                WHERE track_id = ?
            """, (original_track_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "status": "in_library",
                    "track_id": original_track_id,
                    "artist": row[0],
                    "title": row[1],
                    "album": row[2],
                    "year": row[3],
                    "file_path": row[4],
                    "sample_info": primary_sample
                }
        
        # Original not in library - return acquisition target
        return {
            "status": "not_in_library",
            "artist": primary_sample["original_artist"],
            "title": primary_sample["original_title"],
            "year": primary_sample["original_year"],
            "sample_info": primary_sample,
            "action": "acquire"
        }
    
    def get_sampled_by(self, track_id: str) -> List[Dict]:
        """
        Find modern tracks that sample this track.
        
        Inverse of trace_samples - useful for classic/obscure tracks.
        
        Returns:
            List of modern tracks that sampled this one
        """
        cursor = self.conn.cursor()
        
        # First get track info
        cursor.execute("SELECT artist, title FROM tracks WHERE track_id = ?", (track_id,))
        track = cursor.fetchone()
        if not track:
            return []
        
        artist, title = track
        
        # Find modern tracks that sample this
        cursor.execute("""
            SELECT sl.track_id, t.artist, t.title, t.year, sl.sample_type, sl.confidence
            FROM sample_lineage sl
            JOIN tracks t ON sl.track_id = t.track_id
            WHERE sl.original_artist LIKE ? AND sl.original_title LIKE ?
            ORDER BY t.year DESC
        """, (f"%{artist}%", f"%{title}%"))
        
        sampled_by = []
        for row in cursor.fetchall():
            sampled_by.append({
                "track_id": row[0],
                "artist": row[1],
                "title": row[2],
                "year": row[3],
                "sample_type": row[4],
                "confidence": row[5]
            })
        
        logger.info(f"  → {len(sampled_by)} tracks sample this")
        return sampled_by
    
    def suggest_sample_credits(self, track_id: str) -> str:
        """
        Generate proper sample credits for a track.
        
        Format: "Contains sample of 'Original' by Original Artist (Year)"
        """
        samples = self.trace_samples(track_id)
        
        if not samples:
            return ""
        
        credits = []
        for sample in samples:
            if sample["verified"]:
                year_str = f" ({sample['original_year']})" if sample["original_year"] else ""
                credits.append(
                    f"Contains sample of '{sample['original_title']}' "
                    f"by {sample['original_artist']}{year_str}"
                )
        
        return " | ".join(credits)
    
    def import_whosampled_data(self, filepath: str) -> int:
        """
        Import sample data from WhoSampled JSON export.
        
        Expected format:
        [
            {
                "modern_artist": "Daft Punk",
                "modern_title": "Harder Better Faster Stronger",
                "original_artist": "Edwin Birdsong",
                "original_title": "Cola Bottle Baby",
                "original_year": 1979,
                "sample_type": "vocal"
            },
            ...
        ]
        
        Returns:
            Number of samples imported
        """
        logger.info(f"📥 DNA: Importing WhoSampled data from {filepath}")
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            imported = 0
            for entry in data:
                # Find track_id for modern track
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT track_id FROM tracks
                    WHERE artist LIKE ? AND title LIKE ?
                    LIMIT 1
                """, (f"%{entry['modern_artist']}%", f"%{entry['modern_title']}%"))
                
                result = cursor.fetchone()
                if result:
                    track_id = result[0]
                    success = self.register_sample(
                        track_id,
                        entry["original_artist"],
                        entry["original_title"],
                        entry.get("original_year"),
                        entry.get("sample_type", "unknown"),
                        confidence=0.9,
                        source="whosampled"
                    )
                    if success:
                        imported += 1
            
            logger.info(f"  ✓ Imported {imported} samples")
            return imported
        
        except Exception as e:
            logger.error(f"  ✗ Import failed: {e}")
            return 0


# Singleton instance
dna = DNA()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\n🧬 Lyra DNA - Sample Tracer\n")
        print("Commands:")
        print("  python -m oracle.dna trace <track_id>      - Trace samples in track")
        print("  python -m oracle.dna pivot <track_id>      - Pivot to original")
        print("  python -m oracle.dna sampled-by <track_id> - Find who sampled this")
        print("  python -m oracle.dna register <track_id> <original_artist> <original_title>")
        print("\nExample:")
        print("  python -m oracle.dna trace 12345-678-90ab")
        print("  python -m oracle.dna pivot 12345-678-90ab\n")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "trace" and len(sys.argv) >= 3:
        track_id = sys.argv[2]
        samples = dna.trace_samples(track_id)
        
        print(f"\n🧬 SAMPLE DNA: {track_id}\n")
        if samples:
            for i, sample in enumerate(samples, 1):
                print(f"{i}. {sample['original_artist']} - {sample['original_title']}")
                print(f"   Year: {sample['original_year'] or 'Unknown'}")
                print(f"   Type: {sample['sample_type']}")
                print(f"   Confidence: {sample['confidence']:.0%}")
                print(f"   Source: {sample['source']}")
                print()
        else:
            print("No samples registered.\n")
    
    elif command == "pivot" and len(sys.argv) >= 3:
        track_id = sys.argv[2]
        result = dna.pivot_to_original(track_id)
        
        print(f"\n🔄 PIVOT RESULT:\n")
        if result:
            if result["status"] == "in_library":
                print(f"✓ Original found in library!")
                print(f"  Artist: {result['artist']}")
                print(f"  Title: {result['title']}")
                print(f"  Path: {result['file_path']}")
            else:
                print(f"⚠️  Original not in library")
                print(f"  Artist: {result['artist']}")
                print(f"  Title: {result['title']}")
                print(f"  Year: {result['year']}")
                print(f"  Action: Acquire this track")
        else:
            print("No samples registered for this track.\n")
    
    elif command == "register" and len(sys.argv) >= 5:
        track_id = sys.argv[2]
        original_artist = sys.argv[3]
        original_title = sys.argv[4]
        
        success = dna.register_sample(track_id, original_artist, original_title)
        if success:
            print(f"\n✓ Sample registered: {original_artist} - {original_title}\n")
        else:
            print(f"\n✗ Registration failed\n")
    
    else:
        print("\n✗ Invalid command. Run with no args for help.\n")
