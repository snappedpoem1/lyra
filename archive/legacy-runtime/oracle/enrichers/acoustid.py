"""AcoustID fingerprint-first identification provider.

Phase 1 of the zero-trust pipeline: generate Chromaprint fingerprints via
fpcalc, query AcoustID for MusicBrainz Recording IDs (MBIDs), and assign
a confidence tier:

    HIGH   â€” exact MBID match with AcoustID score >= 0.85
    MEDIUM â€” multiple candidates, requires duration/tag cross-referencing
    LOW    â€” no match, fallback to text-based search

System invariants:
    - Never trusts existing ID3 tags for identification
    - Deterministic: same audio bytes always produce same fingerprint
    - All network calls use exponential backoff + rate-limiting
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from oracle.config import ACOUSTID_API_KEY, FPCALC_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACOUSTID_API_URL = "https://api.acoustid.org/v2/lookup"
_MAX_RETRIES = 4
_RATE_LIMIT_SECONDS = 0.34  # ~3 req/s (AcoustID allows ~3/s with key)
_LAST_REQUEST_TS = 0.0


class Confidence(str, Enum):
    """Fingerprint match confidence tier."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FingerprintResult:
    """Result of fingerprinting + AcoustID lookup for a single file."""

    filepath: str
    fingerprint: Optional[str] = None
    duration: Optional[int] = None
    confidence: Confidence = Confidence.LOW
    recording_mbid: Optional[str] = None
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    acoustid_score: float = 0.0
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def score(self) -> float:
        """Backward-compatible alias for acoustid_score."""
        return self.acoustid_score

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        return d


# ---------------------------------------------------------------------------
# fpcalc location
# ---------------------------------------------------------------------------

def _find_fpcalc() -> str:
    """Locate the fpcalc binary.

    Checks:
        1. FPCALC_PATH env var
        2. ``fpcalc`` on PATH (shutil.which)

    Returns:
        Absolute path to fpcalc executable.

    Raises:
        FileNotFoundError: if fpcalc cannot be located.
    """
    if FPCALC_PATH and Path(FPCALC_PATH).is_file():
        return FPCALC_PATH

    found = shutil.which("fpcalc")
    if found:
        return found

    raise FileNotFoundError(
        "fpcalc not found. Install Chromaprint (https://acoustid.org/chromaprint) "
        "or set FPCALC_PATH in .env"
    )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _respect_rate_limit() -> None:
    global _LAST_REQUEST_TS
    elapsed = time.monotonic() - _LAST_REQUEST_TS
    wait = max(0.0, _RATE_LIMIT_SECONDS - elapsed)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_TS = time.monotonic()


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def fingerprint_file(file_path: Path, duration_limit: int = 120) -> Optional[Tuple[str, int]]:
    """Generate a Chromaprint fingerprint for an audio file.

    Args:
        file_path: Path to the audio file.
        duration_limit: Max seconds of audio to fingerprint (default 120).

    Returns:
        (fingerprint_string, duration_seconds) or None on failure.
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        logger.warning("fingerprint_file: file not found: %s", file_path)
        return None

    try:
        fpcalc = _find_fpcalc()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return None

    try:
        result = subprocess.run(
            [fpcalc, "-json", "-length", str(duration_limit), str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.debug(
                "fpcalc returned %d for %s: %s",
                result.returncode, file_path.name, result.stderr.strip(),
            )
            return None

        if not result.stdout.strip():
            logger.debug("fpcalc returned empty output for %s", file_path.name)
            return None

        parsed = json.loads(result.stdout)
        fp = parsed.get("fingerprint")
        dur = parsed.get("duration")

        if not fp or dur is None:
            logger.debug("fpcalc missing fingerprint/duration for %s", file_path.name)
            return None

        return fp, int(dur)

    except subprocess.TimeoutExpired:
        logger.warning("fpcalc timed out for %s", file_path.name)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("fpcalc invalid JSON for %s: %s", file_path.name, exc)
        return None
    except Exception as exc:
        logger.warning("fpcalc unexpected error for %s: %s", file_path.name, exc)
        return None


def lookup_fingerprint(
    fingerprint: str,
    duration: int,
    meta: str = "recordings+releasegroups+compress",
) -> Dict[str, Any]:
    """Query AcoustID API for recording matches.

    Args:
        fingerprint: Chromaprint fingerprint string.
        duration: Audio duration in seconds.
        meta: AcoustID meta fields to request.

    Returns:
        Raw AcoustID API response dict, or empty dict on failure.
    """
    if not ACOUSTID_API_KEY:
        logger.error("ACOUSTID_API_KEY not set â€” cannot query AcoustID")
        return {}

    params = {
        "client": ACOUSTID_API_KEY,
        "meta": meta,
        "duration": str(int(duration)),
        "fingerprint": fingerprint,
        "format": "json",
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _respect_rate_limit()
            response = requests.get(
                ACOUSTID_API_URL,
                params=params,
                timeout=30,
                headers={"User-Agent": "LyraOracle/1.0 (lyra@oracle.local)"},
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                backoff = min(16.0, 2 ** attempt)
                logger.debug(
                    "AcoustID %d on attempt %d, backing off %.1fs",
                    response.status_code, attempt, backoff,
                )
                time.sleep(backoff)
                continue

            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                logger.warning("AcoustID non-ok status: %s", data.get("status"))
                return {}

            return data

        except requests.HTTPError as exc:
            logger.warning("AcoustID HTTP error attempt %d: %s", attempt, exc)
            time.sleep(min(16.0, 2 ** attempt))
        except requests.RequestException as exc:
            logger.warning("AcoustID request error attempt %d: %s", attempt, exc)
            time.sleep(min(16.0, 2 ** attempt))

    logger.warning("AcoustID lookup failed after %d attempts", _MAX_RETRIES)
    return {}


# ---------------------------------------------------------------------------
# High-level identification
# ---------------------------------------------------------------------------

def _extract_best_recording(
    results: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], float, List[Dict[str, Any]]]:
    """Extract the best recording match from AcoustID results.

    Returns:
        (best_recording, best_score, all_candidates)
    """
    candidates: List[Dict[str, Any]] = []
    best_recording: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for result in results:
        score = float(result.get("score", 0))
        for recording in result.get("recordings", []):
            mbid = recording.get("id")
            if not mbid:
                continue

            artists = recording.get("artists", [])
            artist_name = "; ".join(a.get("name", "") for a in artists) if artists else None

            release_groups = recording.get("releasegroups", [])
            album_name = None
            year = None
            if release_groups:
                rg = release_groups[0]
                album_name = rg.get("title")
                # Extract year from first release date
                releases = rg.get("releases", [])
                for rel in releases:
                    date_str = rel.get("date", {})
                    if isinstance(date_str, dict):
                        y = date_str.get("year")
                    else:
                        y = str(date_str)[:4] if date_str else None
                    if y:
                        year = str(y)
                        break

            candidate = {
                "recording_mbid": mbid,
                "title": recording.get("title"),
                "artist": artist_name,
                "album": album_name,
                "year": year,
                "score": score,
            }
            candidates.append(candidate)

            if score > best_score:
                best_score = score
                best_recording = candidate

    return best_recording, best_score, candidates


def identify_file(
    file_path: Path,
    existing_artist: Optional[str] = None,
    existing_title: Optional[str] = None,
    existing_duration: Optional[float] = None,
) -> FingerprintResult:
    """Full fingerprint-first identification for a single audio file.

    This is the primary entry point for Phase 1. It:
        1. Generates a Chromaprint fingerprint (bypasses all tags)
        2. Queries AcoustID for MusicBrainz Recording IDs
        3. Assigns a confidence tier based on match quality
        4. For MEDIUM confidence, cross-references duration + existing tags

    Args:
        file_path: Path to the audio file.
        existing_artist: Current artist tag (for cross-referencing only).
        existing_title: Current title tag (for cross-referencing only).
        existing_duration: Current duration in seconds (for cross-referencing).

    Returns:
        FingerprintResult with confidence tier and best match data.
    """
    file_path = Path(file_path)
    result = FingerprintResult(filepath=str(file_path))

    # Step 1: Generate fingerprint
    fp_data = fingerprint_file(file_path)
    if fp_data is None:
        result.error = "fingerprint generation failed"
        result.confidence = Confidence.LOW
        return result

    fingerprint, duration = fp_data
    result.fingerprint = fingerprint
    result.duration = duration

    # Step 2: Query AcoustID
    api_response = lookup_fingerprint(fingerprint, duration)
    if not api_response:
        result.error = "acoustid lookup returned no data"
        result.confidence = Confidence.LOW
        return result

    results = api_response.get("results", [])
    if not results:
        result.error = "no acoustid results"
        result.confidence = Confidence.LOW
        return result

    # Step 3: Extract candidates and assign confidence
    best, best_score, candidates = _extract_best_recording(results)
    result.candidates = candidates
    result.acoustid_score = best_score

    if best is None:
        result.error = "no recordings in results"
        result.confidence = Confidence.LOW
        return result

    result.recording_mbid = best["recording_mbid"]
    result.artist = best.get("artist")
    result.title = best.get("title")
    result.album = best.get("album")
    result.year = best.get("year")

    # Confidence assignment
    if best_score >= 0.85 and len(candidates) <= 3:
        # HIGH: strong fingerprint match, few ambiguous candidates
        result.confidence = Confidence.HIGH

    elif best_score >= 0.50:
        # MEDIUM: decent match but may need cross-referencing
        result.confidence = Confidence.MEDIUM

        # Cross-reference with existing tags to boost or demote
        if existing_duration and result.duration:
            duration_diff = abs(existing_duration - result.duration)
            if duration_diff > 10:
                # Duration mismatch > 10s â€” suspicious
                result.confidence = Confidence.LOW
                result.error = f"duration mismatch: file={existing_duration:.0f}s fp={result.duration}s"

        # Cross-reference existing artist/title with best candidate
        if existing_artist and result.artist:
            from difflib import SequenceMatcher

            artist_sim = SequenceMatcher(
                None,
                existing_artist.lower().strip(),
                result.artist.lower().strip(),
            ).ratio()
            if artist_sim >= 0.7:
                # Tag agrees with fingerprint â€” boost to HIGH if score is decent
                if best_score >= 0.70:
                    result.confidence = Confidence.HIGH
    else:
        # LOW: weak match
        result.confidence = Confidence.LOW
        result.error = f"low acoustid score: {best_score:.2f}"

    return result


def identify_batch(
    file_paths: List[Path],
    batch_delay: float = 0.5,
) -> List[FingerprintResult]:
    """Identify multiple files with rate-limited AcoustID lookups.

    Args:
        file_paths: List of audio file paths.
        batch_delay: Extra delay between files (on top of rate limit).

    Returns:
        List of FingerprintResult objects.
    """
    results: List[FingerprintResult] = []
    total = len(file_paths)

    for i, fp in enumerate(file_paths, 1):
        logger.info("Fingerprinting %d/%d: %s", i, total, Path(fp).name)
        result = identify_file(fp)
        results.append(result)

        if i < total and batch_delay > 0:
            time.sleep(batch_delay)

    # Summary logging
    high = sum(1 for r in results if r.confidence == Confidence.HIGH)
    med = sum(1 for r in results if r.confidence == Confidence.MEDIUM)
    low = sum(1 for r in results if r.confidence == Confidence.LOW)
    logger.info(
        "Fingerprint batch complete: %d total, %d high, %d medium, %d low",
        total, high, med, low,
    )

    return results

