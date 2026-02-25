"""
The Architect - Audio Structure Analysis

"See the music before you hear it."

Features:
- Structure mapping (Intro/Verse/Chorus/Drop/Outro)
- Drop detection (16-bar buildup + sub-bass spike)
- BPM extraction
- Key detection
- Energy profile (per-second intensity)
- Harmonic/Percussive separation

Enables:
- Waveform visualization with colored segments
- Smart mixing (match drops between tracks)
- Energy-based search

Author: Lyra Oracle v9.0
"""

<<<<<<< HEAD
import os
import logging
import sqlite3
=======
import logging
>>>>>>> fc77b41 (Update workspace state and diagnostics)
import json
import numpy as np
from typing import Optional, List, Dict, Tuple
from datetime import datetime
<<<<<<< HEAD
from pathlib import Path
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)

try:
    import librosa
    try:
        import librosa.display
    except Exception:
        # Optional dependency for visualization only.
        pass
except ImportError:
    librosa = None
    logging.warning("librosa not installed. Architect features disabled.")

from oracle.config import get_connection

logger = logging.getLogger(__name__)


class Architect:
    """The Architect - Maps audio structure."""
    
    def __init__(self):
        self.conn = get_connection()
        
        if not librosa:
            logger.warning("⚠️  librosa not available. Install with: pip install librosa")
    
    def analyze_structure(self, track_id: str, file_path: str) -> Dict:
        """
        Analyze track structure and store in database.
        
        Args:
            track_id: Track UUID
            file_path: Path to audio file
        
        Returns:
            Structure analysis dict
        """
        if not librosa:
            return {"error": "librosa_not_installed"}
        
        logger.info(f"🏗️  ARCHITECT: Analyzing structure [{file_path}]")
        
        try:
            # Load audio
            logger.info("  → Loading audio...")
            y, sr = librosa.load(file_path, sr=22050, mono=True, duration=600)  # Max 10 minutes
            
            # Phase 1: BPM Detection
            logger.info("  → Detecting BPM...")
            bpm = self._detect_bpm(y, sr)
            logger.info(f"    BPM: {bpm:.1f}")
            
            # Phase 2: Key Detection
            logger.info("  → Detecting key...")
            key_signature = self._detect_key(y, sr)
            logger.info(f"    Key: {key_signature}")
            
            # Phase 3: Structure Segmentation
            logger.info("  → Segmenting structure...")
            structure = self._segment_structure(y, sr, bpm)
            logger.info(f"    Segments: {len(structure)}")
            
            # Phase 4: Drop Detection
            logger.info("  → Detecting drops...")
            has_drop, drop_time = self._detect_drop(y, sr, structure)
            if has_drop:
                logger.info(f"    DROP at {drop_time:.1f}s 💥")
            
            # Phase 5: Energy Profile
            logger.info("  → Generating energy profile...")
            energy_profile = self._generate_energy_profile(y, sr)
            
            # Store in database
            self._store_structure(
                track_id,
                structure,
                has_drop,
                drop_time,
                bpm,
                key_signature,
                energy_profile
            )
            
            logger.info("  ✓ Analysis complete")
            
            return {
                "track_id": track_id,
                "bpm": bpm,
                "key": key_signature,
                "structure": structure,
                "has_drop": has_drop,
                "drop_timestamp": drop_time,
                "energy_profile": energy_profile[:60],  # First 60 seconds for preview
                "analyzed_at": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"  ✗ Analysis failed: {e}")
            return {"error": str(e)}
    
    def _detect_bpm(self, y: np.ndarray, sr: int) -> float:
        """Detect tempo (BPM) using onset detection."""
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return float(tempo)
    
    def _detect_key(self, y: np.ndarray, sr: int) -> str:
        """
        Detect musical key using chroma features.
        
        Returns key in format: "C", "Am", "F#", etc.
        """
        # Compute chromagram
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        
        # Average chroma over time
        chroma_mean = np.mean(chroma, axis=1)
        
        # Find dominant pitch class
        dominant_pitch = np.argmax(chroma_mean)
        
        # Pitch class to note mapping
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # Simple major/minor detection (rough heuristic)
        # Check if minor third is prominent
        minor_third = (dominant_pitch + 3) % 12
        is_minor = chroma_mean[minor_third] > chroma_mean.mean()
        
        note = notes[dominant_pitch]
        return f"{note}m" if is_minor else note
    
    def _segment_structure(self, y: np.ndarray, sr: int, bpm: float) -> List[Dict]:
        """
        Segment track into structural components using recurrence matrix.
        
        Returns:
            List of segments with labels and timestamps
        """
        # Compute MFCC features
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        
        # Compute recurrence matrix
<<<<<<< HEAD
        R = librosa.segment.recurrence_matrix(
=======
        librosa.segment.recurrence_matrix(
>>>>>>> fc77b41 (Update workspace state and diagnostics)
            mfcc,
            mode='affinity',
            metric='cosine',
            width=43  # ~2 seconds at 22050 Hz
        )
        
        # Detect segment boundaries
        boundaries = librosa.segment.agglomerative(mfcc, k=8)  # Max 8 segments
        boundary_times = librosa.frames_to_time(boundaries, sr=sr)
        
        # Label segments
        structure = []
        labels = ['intro', 'verse', 'buildup', 'drop', 'verse', 'bridge', 'drop', 'outro']
        
        for i, (start, end) in enumerate(zip(boundary_times[:-1], boundary_times[1:])):
            label = labels[i] if i < len(labels) else 'section'
            
            structure.append({
                'label': label,
                'start': float(start),
                'end': float(end),
                'duration': float(end - start),
                'color': self._get_segment_color(label)
            })
        
        return structure
    
    def _detect_drop(
        self,
        y: np.ndarray,
        sr: int,
        structure: List[Dict]
    ) -> Tuple[bool, Optional[float]]:
        """
        Detect "drop" moments in electronic music.
        
        Drop characteristics:
        - Preceded by 16+ bars of rising energy (buildup)
        - Sudden spike in sub-bass (20-200 Hz)
        - High spectral flux
        - Percussive energy increase
        
        Returns:
            (has_drop, timestamp)
        """
        # Harmonic-percussive separation
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        
        # Compute spectral flux (measure of change)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        
        # Smooth onset envelope
        onset_smooth = librosa.util.normalize(onset_env)
        
        # Find peaks (potential drops)
        peaks = librosa.util.peak_pick(
            onset_smooth,
            pre_max=20,
            post_max=20,
            pre_avg=20,
            post_avg=20,
            delta=0.3,
            wait=44  # ~1 second
        )
        
        if len(peaks) == 0:
            return False, None
        
        # Analyze each peak
        for peak in peaks:
            peak_time = librosa.frames_to_time(peak, sr=sr)
            
            # Check if preceded by buildup
            buildup_start = max(0, peak - int(16 * sr / 512))  # ~16 bars before
            buildup_energy = onset_smooth[buildup_start:peak]
            
            if len(buildup_energy) > 0:
                # Rising energy trend?
                energy_slope = np.polyfit(range(len(buildup_energy)), buildup_energy, 1)[0]
                
                if energy_slope > 0.01:  # Positive slope = buildup
                    # Check sub-bass spike at drop
                    drop_start = int(peak_time * sr)
                    drop_window = y[drop_start:drop_start + sr]  # 1 second
                    
                    if len(drop_window) > 0:
                        # FFT to check sub-bass
                        freqs = np.fft.rfftfreq(len(drop_window), 1/sr)
                        fft = np.abs(np.fft.rfft(drop_window))
                        
                        # Energy in 20-200 Hz range
                        sub_bass_mask = (freqs >= 20) & (freqs <= 200)
                        sub_bass_energy = np.sum(fft[sub_bass_mask])
                        
                        total_energy = np.sum(fft)
                        sub_bass_ratio = sub_bass_energy / total_energy if total_energy > 0 else 0
                        
                        if sub_bass_ratio > 0.15:  # Strong sub-bass presence
                            logger.info(f"    → DROP detected: Buildup slope={energy_slope:.3f}, Sub-bass={sub_bass_ratio:.2%}")
                            return True, float(peak_time)
        
        return False, None
    
    def _generate_energy_profile(self, y: np.ndarray, sr: int) -> List[float]:
        """
        Generate per-second energy profile.
        
        Returns:
            List of energy values (0.0-1.0) for each second
        """
        # RMS energy per second
        hop_length = sr  # 1 second
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        
        # Normalize to 0-1
        rms_normalized = rms / (np.max(rms) + 1e-6)
        
        return rms_normalized.tolist()
    
    def _get_segment_color(self, label: str) -> str:
        """Map segment label to color for visualization."""
        color_map = {
            'intro': '#4A90E2',      # Blue
            'verse': '#7ED321',      # Green
            'buildup': '#F5A623',    # Orange
            'drop': '#FF3366',       # Neon Red
            'bridge': '#9013FE',     # Purple
            'outro': '#50E3C2',      # Teal
            'section': '#B8B8B8'     # Gray
        }
        return color_map.get(label, '#B8B8B8')
    
    def _store_structure(
        self,
        track_id: str,
        structure: List[Dict],
        has_drop: bool,
        drop_time: Optional[float],
        bpm: float,
        key: str,
        energy_profile: List[float]
    ) -> None:
        """Store structure analysis in database."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO track_structure
                (track_id, structure_json, has_drop, drop_timestamp, bpm, key_signature, energy_profile)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                track_id,
                json.dumps(structure),
                has_drop,
                drop_time,
                bpm,
                key,
                json.dumps(energy_profile)
            ))
            self.conn.commit()
            logger.info("  → Structure stored in database")
        
        except Exception as e:
            logger.error(f"  ✗ Failed to store structure: {e}")
    
    def get_structure(self, track_id: str) -> Optional[Dict]:
        """Retrieve stored structure analysis."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT structure_json, has_drop, drop_timestamp, bpm, key_signature, energy_profile
            FROM track_structure
            WHERE track_id = ?
        """, (track_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                "structure": json.loads(row[0]),
                "has_drop": bool(row[1]),
                "drop_timestamp": row[2],
                "bpm": row[3],
                "key": row[4],
                "energy_profile": json.loads(row[5]) if row[5] else []
            }
        
        return None
    
    def find_drop_tracks(self, limit: int = 50) -> List[Dict]:
        """Find all tracks with detected drops."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.track_id, t.artist, t.title, ts.drop_timestamp, ts.bpm
            FROM tracks t
            JOIN track_structure ts ON t.track_id = ts.track_id
            WHERE ts.has_drop = 1
            ORDER BY ts.drop_timestamp ASC
            LIMIT ?
        """, (limit,))
        
        drops = []
        for row in cursor.fetchall():
            drops.append({
                "track_id": row[0],
                "artist": row[1],
                "title": row[2],
                "drop_time": row[3],
                "bpm": row[4]
            })
        
        return drops


# Singleton instance
architect = Architect()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\n🏗️  Lyra Architect - Audio Structure Analysis\n")
        print("Commands:")
        print("  python -m oracle.architect analyze <track_id> <file_path>")
        print("  python -m oracle.architect get <track_id>")
        print("  python -m oracle.architect drops")
        print("\nExample:")
        print("  python -m oracle.architect analyze abc123 'music/track.mp3'")
        print("  python -m oracle.architect get abc123")
        print("  python -m oracle.architect drops\n")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "analyze" and len(sys.argv) >= 4:
        track_id = sys.argv[2]
        file_path = sys.argv[3]
        
        result = architect.analyze_structure(track_id, file_path)
        
        if "error" not in result:
            print(f"\n🏗️  STRUCTURE ANALYSIS:\n")
            print(f"BPM: {result['bpm']:.1f}")
            print(f"Key: {result['key']}")
            print(f"Drop: {'YES 💥 at ' + str(result['drop_timestamp']) + 's' if result['has_drop'] else 'NO'}")
            print(f"\nSegments: {len(result['structure'])}")
            for seg in result['structure']:
                print(f"  [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['label']}")
        else:
            print(f"\n✗ Analysis failed: {result['error']}\n")
    
    elif command == "get" and len(sys.argv) >= 3:
        track_id = sys.argv[2]
        structure = architect.get_structure(track_id)
        
        if structure:
            print(f"\n🏗️  STORED STRUCTURE:\n")
            print(json.dumps(structure, indent=2))
        else:
            print(f"\n✗ No structure analysis found for track {track_id}\n")
    
    elif command == "drops":
        drops = architect.find_drop_tracks(50)
        
        print(f"\n💥 TRACKS WITH DROPS: {len(drops)}\n")
        for i, drop in enumerate(drops, 1):
            print(f"{i:2}. {drop['artist']} - {drop['title']}")
            print(f"    Drop at {drop['drop_time']:.1f}s | BPM: {drop['bpm']:.0f}")
        print()
    
    else:
        print("\n✗ Invalid command. Run with no args for help.\n")
