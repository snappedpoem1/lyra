"""Essentia audio analysis enricher.

Maps Essentia's acoustic descriptors to Oracle's 10 emotional dimensions
for score validation and enrichment.

Requires:
    Essentia Docker service running on port 7701
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_ESSENTIA_URL = os.getenv("ESSENTIA_URL", "http://localhost:7701")
_TIMEOUT = 30


def is_available() -> bool:
    """Check if Essentia Docker service is reachable."""
    try:
        resp = requests.get(f"{_ESSENTIA_URL}/health", timeout=5)
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        return False


def analyze_file(filepath: Path) -> Optional[Dict[str, Any]]:
    """Upload audio file to Essentia service and get raw descriptors.
    
    Args:
        filepath: Path to audio file.
        
    Returns:
        Dict of raw Essentia descriptors, or None on error.
    """
    if not filepath.exists():
        logger.error(f"[Essentia] File not found: {filepath}")
        return None
    
    try:
        with open(filepath, "rb") as f:
            files = {"file": (filepath.name, f, "audio/mpeg")}
            resp = requests.post(
                f"{_ESSENTIA_URL}/analyze",
                files=files,
                timeout=_TIMEOUT,
            )
        
        if resp.status_code != 200:
            logger.warning(f"[Essentia] Service returned {resp.status_code}")
            return None
        
        data = resp.json()
        if not data.get("success"):
            logger.warning(f"[Essentia] Analysis failed: {data.get('error')}")
            return None
        
        return data.get("descriptors", {})
    
    except Exception as exc:
        logger.warning(f"[Essentia] Request failed: {exc}")
        return None


def map_to_dimensions(descriptors: Dict[str, Any]) -> Dict[str, float]:
    """Convert Essentia descriptors to Oracle's 10-dimensional scores [0,1].
    
    Dimension mapping:
        energy     ← loudness, dynamic_complexity
        valence    ← key mode (major=higher), danceability
        tension    ← dissonance, spectral_complexity
        density    ← spectral_complexity, loudness
        warmth     ← spectral_centroid (inverse - lower = warmer)
        movement   ← danceability, bpm
        space      ← spectral_flatness (inverse - lower = more reverb/space)
        rawness    ← spectral_flatness (higher = more raw)
        complexity ← spectral_complexity, key_strength (inverse)
        nostalgia  ← spectral_rolloff heuristic (lower rolloff = older production)
    
    Args:
        descriptors: Raw Essentia output from analyze_file().
        
    Returns:
        Dict mapping dimension names to scores [0,1].
    """
    import math
    
    dims: Dict[str, float] = {}
    
    # Energy: loudness + dynamic complexity
    loudness = descriptors.get("loudness", 0.0)
    integrated_loud = descriptors.get("integrated_loudness", -23.0)  # LUFS
    dynamic_complexity = descriptors.get("dynamic_complexity", 0.0)
    
    # Normalize loudness from LUFS (-70 to 0) to [0,1]
    loud_norm = max(0.0, min(1.0, (integrated_loud + 70.0) / 70.0))
    # Dynamic complexity is 0-1 already
    dims["energy"] = (loud_norm * 0.6 + dynamic_complexity * 0.4)
    
    # Valence: key mode + danceability
    scale = descriptors.get("scale", "minor")
    danceability = descriptors.get("danceability", 0.5)
    key_mode_boost = 0.15 if scale == "major" else -0.10
    dims["valence"] = max(0.0, min(1.0, danceability * 0.7 + 0.3 + key_mode_boost))
    
    # Tension: dissonance + spectral complexity
    dissonance = descriptors.get("dissonance", 0.0)  # typically 0-1
    spectral_complexity = descriptors.get("spectral_complexity", 0.0)  # 0-1
    dims["tension"] = (dissonance * 0.6 + spectral_complexity * 0.4)
    
    # Density: spectral complexity + loudness
    dims["density"] = (spectral_complexity * 0.5 + loud_norm * 0.5)
    
    # Warmth: inverse of spectral centroid (lower centroid = warmer timbre)
    centroid = descriptors.get("spectral_centroid", 2000.0)  # Hz, typical range 500-8000
    centroid_norm = max(0.0, min(1.0, (centroid - 500.0) / 7500.0))
    dims["warmth"] = 1.0 - centroid_norm
    
    # Movement: danceability + BPM
    bpm = descriptors.get("bpm", 120.0)
    bpm_norm = max(0.0, min(1.0, (bpm - 60.0) / 120.0))  # 60-180 BPM → 0-1
    dims["movement"] = (danceability * 0.7 + bpm_norm * 0.3)
    
    # Space: inverse of spectral flatness (more reverb = less flat = lower flatness)
    flatness = descriptors.get("spectral_flatness", 0.0)  # 0-1
    dims["space"] = 1.0 - flatness
    
    # Rawness: spectral flatness (higher = more raw/noise-like)
    dims["rawness"] = flatness
    
    # Complexity: spectral complexity + key ambiguity
    key_strength = descriptors.get("key_strength", 0.5)  # 0-1
    key_ambiguity = 1.0 - key_strength  # inverse: weak key = more complex
    dims["complexity"] = (spectral_complexity * 0.6 + key_ambiguity * 0.4)
    
    # Nostalgia: heuristic based on spectral characteristics
    # Lower centroid + lower complexity suggests older production techniques
    nostalgia_score = (dims["warmth"] * 0.5 + (1.0 - spectral_complexity) * 0.3 + 0.2)
    dims["nostalgia"] = max(0.0, min(1.0, nostalgia_score))
    
    return dims


def validate_scores(
    clap_scores: Dict[str, float],
    essentia_scores: Dict[str, float],
    threshold: float = 0.3,
) -> Dict[str, Any]:
    """Compare CLAP-based scores against Essentia-based scores.
    
    Flags dimensions where the two methods disagree significantly,
    which may indicate scoring issues or edge cases.
    
    Args:
        clap_scores: CLAP-based dimension scores [0,1].
        essentia_scores: Essentia-based dimension scores [0,1].
        threshold: Divergence threshold to flag (default 0.3).
        
    Returns:
        Dict with keys: divergent_dimensions, max_divergence, mean_divergence.
    """
    divergences: List[tuple[str, float, float, float]] = []
    
    for dim in clap_scores.keys():
        if dim not in essentia_scores:
            continue
        
        clap_val = clap_scores[dim]
        ess_val = essentia_scores[dim]
        diff = abs(clap_val - ess_val)
        
        if diff >= threshold:
            divergences.append((dim, clap_val, ess_val, diff))
    
    divergences.sort(key=lambda x: x[3], reverse=True)
    
    all_diffs = [abs(clap_scores.get(d, 0.5) - essentia_scores.get(d, 0.5)) for d in clap_scores]
    mean_div = sum(all_diffs) / len(all_diffs) if all_diffs else 0.0
    max_div = max(all_diffs) if all_diffs else 0.0
    
    return {
        "divergent_dimensions": [
            {
                "dimension": d,
                "clap": round(c, 3),
                "essentia": round(e, 3),
                "difference": round(diff, 3),
            }
            for d, c, e, diff in divergences
        ],
        "max_divergence": round(max_div, 3),
        "mean_divergence": round(mean_div, 3),
    }


def build_track_profile(filepath: Path) -> Optional[Dict[str, Any]]:
    """Analyze audio file and return both raw descriptors and mapped dimensions.
    
    This is the main entry point for the enricher.
    
    Args:
        filepath: Path to audio file.
        
    Returns:
        Dict with keys: descriptors, dimensions, or None on error.
    """
    descriptors = analyze_file(filepath)
    if not descriptors:
        return None
    
    dimensions = map_to_dimensions(descriptors)
    
    return {
        "descriptors": descriptors,
        "dimensions": dimensions,
    }
