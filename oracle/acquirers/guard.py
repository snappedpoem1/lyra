"""Acquisition Guard - Pre-flight checks before ANY track enters the library.

This is the GATEKEEPER. Every track must pass through here before being added.
No exceptions. No bypasses.

Checks:
1. REJECT junk (karaoke, tribute, 8-bit, ringtones)
2. REJECT record labels as artists
3. REJECT YouTube channels as artists  
4. VALIDATE against MusicBrainz/Discogs (real track?)
5. NORMALIZE metadata before acceptance
6. DETECT duplicates
7. VERIFY audio quality
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# BLACKLISTS - Instant rejection
# =============================================================================

# Junk patterns - REJECT if found anywhere in artist OR title
JUNK_PATTERNS: List[str] = [
    # Karaoke/covers/backing tracks
    r'\bkaraoke\b',
    r'\btribute\s*(to|band|players)?\b',
    r'\bcover\s+version\b',
    r'\bcover(?:ed)?\s+by\b',
    r'\bmade\s*famous\b',
    r'\bmade\s*popular\b',
    r'\bin\s*the\s*style\s*of\b',
    r'\boriginally\s*performed\b',
    r'\bpiano\s*(tribute|version|cover)\b',
    r'\bacoustic\s*tribute\b',
    r'\borchestral\s*tribute\b',
    r'\bbacking\s*(version|track|vocal)?\b',

    # Specific junk artists (full band names -- safe to match anywhere)
    r'\bparty\s*tyme\b',
    r'\bprosource\b',
    r'\bzzang\b',
    r'\btwinkle\s*twinkle\s*little\s*rock\s*star\b',
    r'\bvitamin\s*string\s*quartet\b',
    r'\brockabye\s*baby\b',
    r'\bscala\s*&\s*kolacny\b',

    # YouTube spam
    r'\blyrics?\s*video\b',
    r'\baudio\s*only\b',
    r'\b1\s*hour\s*(loop|version|mix)\b',
    r'\bslowed\s*(\+|and|\&)?\s*reverb\b',
    r'\bnightcore\b',
    r'\bsped\s*up\b',
    r'\bchopped\s*(and|&|n)?\s*screwed\b',
    r'\bchopped\s*not\s*slopped\b',
]

# Title-only junk patterns -- content descriptors that could legitimately be part
# of a band name (e.g. "A Static Lullaby", "8-Bit Misfits") but are junk when
# they appear in a track or album title.
TITLE_JUNK_PATTERNS: List[str] = [
    r'\b8[- ]?bit\b',
    r'\bmidi\b',
    r'\bringtone\b',
    r'\bmusic\s*box\b',
    r'\blullaby\s*(version|mix|edit|cover)?\b',
    r'[\(\[]\s*cover\s*[\)\]]',

    # Instrumental/stripped versions (the user wants the actual song)
    r'[-â€“(]\s*instrumental\b',
    r'\binstrumental\s+(version|mix|edit)\b',
    r'[-â€“(]\s*a\s*cappella\b',
    r'[-â€“(]\s*acapella\b',
    r'\ba\s*cappella\s+(version|mix|edit)\b',
    r'\bacapella\s+(version|mix|edit)\b',

    # Lofi remakes by random channels
    r'\(lo-?fi\)',
    r'\blo-?fi\s+(version|remix|edit|mix)\b',
    r'[-â€“]\s*lo-?fi\s*$',

    # "Epic Version" / "Rave Version" YouTube remakes
    r'\bepic\s+version\b',
    r'\brave\s+version\b',

    # Classical catalog numbers -- Handel (HWV), Bach (BWV), Purcell (Z.)
    # These indicate classical compositions misattributed to rock/hip-hop artists
    r'\bHWV\s*\d',
    r'\bBWV\s*\d',
    r'\bZ\.\s*\d{3}',
]

# Record labels - NEVER valid as primary artist
RECORD_LABELS: Set[str] = {
    # Major labels
    "atlantic records", "columbia records", "interscope", "def jam",
    "universal music", "sony music", "warner records", "rca records",
    "capitol records", "republic records", "epic records", "island records",
    
    # Rock/alternative labels
    "epitaph records", "epitaph", "vagrant records", "vagrant",
    "fueled by ramen", "hopeless records", "victory records",
    "fearless records", "rise records", "riserecords",
    "equal vision", "tooth & nail", "solid state", "roadrunner records",
    "sumerian records", "spinefarm", "nuclear blast", "metal blade",
    "dine alone records", "dine alone", "pure noise records",
    
    # Hip-hop labels
    "def jam recordings", "aftermath", "top dawg entertainment", "tde",
    "dreamville", "quality control", "owl pharaoh", "odd future",
    
    # YouTube/compilation channels
    "lyrical lemonade", "worldstarhiphop", "wshh", "genius",
    "colors", "colors show", "a]colors show", "vevo",
    "majestic casual", "mrsuicidesheep", "suicide sheep",
    "trap nation", "bass nation", "chill nation",
    "proximity", "monstercat", "ncs", "nocopyrightsounds",
    "the sound you need", "soundcloud", "bandcamp",
    
    # Misc channels
    "official", "officialpsy", "official video", "official audio",
    "topic", "auto-generated", "youtube music",
}

# YouTube channel patterns (regex)
YOUTUBE_CHANNEL_PATTERNS: List[str] = [
    r'^.+\s*-\s*topic$',  # "Artist - Topic" (YouTube Music)
    r'^.+vevo$',  # "ArtistVEVO"
    r'official\s*(channel|page|video|audio)$',
]


# =============================================================================
# GUARD RESULT
# =============================================================================

@dataclass
class GuardResult:
    """Result of acquisition guard check."""
    allowed: bool
    confidence: float  # 0.0 - 1.0
    
    # Cleaned/canonical metadata
    artist: str = ""
    title: str = ""
    album: Optional[str] = None
    year: Optional[int] = None
    genres: List[str] = field(default_factory=list)
    
    # Rejection info
    rejection_reason: Optional[str] = None
    rejection_category: Optional[str] = None  # junk, label, duplicate, invalid, quality
    
    # Validation source
    validated_by: Optional[str] = None  # musicbrainz, discogs, local
    external_id: Optional[str] = None  # MB recording ID, Discogs ID
    
    # Quality info
    is_duplicate: bool = False
    existing_path: Optional[str] = None
    
    # Warnings (allowed but flagged)
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# GUARD FUNCTIONS
# =============================================================================

def _similarity(a: str, b: str) -> float:
    """Calculate string similarity (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _clean_string(s: str) -> str:
    """Normalize string for comparison."""
    if not s:
        return ""
    # Lowercase, remove extra whitespace
    s = re.sub(r'\s+', ' ', s.lower().strip())
    # Remove common punctuation variations
    s = re.sub(r'[\'\"''""]', '', s)
    return s


def _check_junk(artist: str, title: str) -> Optional[Tuple[str, str]]:
    """Check if track matches junk patterns.

    JUNK_PATTERNS are checked against artist+title combined.
    TITLE_JUNK_PATTERNS are checked against title only -- these are content
    descriptors that could legitimately appear in a band name (e.g. "A Static
    Lullaby", "8-Bit Misfits") but signal junk when in a track title.

    Returns:
        (rejection_reason, category) if junk, None if OK
    """
    combined = f"{artist} {title}".lower()
    title_lower = title.lower()

    for pattern in JUNK_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return (f"Matches junk pattern: {pattern}", "junk")

    for pattern in TITLE_JUNK_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return (f"Matches title junk pattern: {pattern}", "junk")

    return None


def _check_record_label(artist: str) -> Optional[Tuple[str, str]]:
    """Check if artist is actually a record label.
    
    Returns:
        (rejection_reason, category) if label, None if OK
    """
    artist_clean = _clean_string(artist)
    
    # Direct match
    if artist_clean in RECORD_LABELS:
        return (f"Artist is a record label: {artist}", "label")
    
    # Partial match (label name in artist)
    for label in RECORD_LABELS:
        if label in artist_clean and len(label) > 5:  # Avoid false positives
            return (f"Artist contains record label: {label}", "label")
    
    # YouTube channel patterns
    for pattern in YOUTUBE_CHANNEL_PATTERNS:
        if re.search(pattern, artist, re.IGNORECASE):
            return (f"Artist is a YouTube channel: {artist}", "label")
    
    return None


def _clean_title(title: str) -> str:
    """Remove YouTube/video cruft from title."""
    if not title:
        return ""
    
    original = title
    
    # Remove video markers
    patterns = [
        r'\s*[\(\[]official\s*(music\s*)?(video|audio|lyric\s*video|visualizer)[\)\]]',
        r'\s*[\(\[]explicit[\)\]]',
        r'\s*[\(\[]clean\s*(version)?[\)\]]',
        r'\s*[\(\[]hd\s*\d*p?[\)\]]',
        r'\s*[\(\[]4k[\)\]]',
        r'\s*[\(\[]lyrics?[\)\]]',
        r'\s*[\(\[]audio[\)\]]',
        r'\s*[\(\[]video[\)\]]',
        r'\s*[\(\[]remaster(ed)?[\)\]]',
        r'\s*-\s*official\s*(music\s*)?(video|audio).*$',
        r'\s*\|\s*[^|]+$',  # Remove " | Channel Name"
        r'\s*[\(\[].*?(?:ft\.?|feat\.?).*?[\)\]]',  # Remove feat in parens
    ]
    
    for pattern in patterns:
        original = re.sub(pattern, '', original, flags=re.IGNORECASE)
    
    return original.strip()


def _clean_artist(artist: str) -> str:
    """Clean up artist name."""
    if not artist:
        return ""
    
    original = artist
    
    # Remove VEVO suffix
    original = re.sub(r'\s*VEVO$', '', original, flags=re.IGNORECASE)
    
    # Remove "- Topic" suffix (YouTube Music)
    original = re.sub(r'\s*-\s*Topic$', '', original, flags=re.IGNORECASE)
    
    # Remove "Official" suffix
    original = re.sub(r'\s*Official$', '', original, flags=re.IGNORECASE)
    
    return original.strip()


def _extract_real_artist_from_title(artist: str, title: str) -> Tuple[str, str]:
    """Try to extract real artist if current artist is a label/channel.
    
    Common pattern: Label uploads "Artist - Song Title"
    """
    # Check if artist looks like a label
    artist_check = _check_record_label(artist)
    if not artist_check:
        return artist, title
    
    # Try to extract from title
    if ' - ' in title:
        parts = title.split(' - ', 1)
        potential_artist = parts[0].strip()
        remaining_title = parts[1].strip() if len(parts) > 1 else ""
        
        # Verify the extracted artist isn't also a label
        if not _check_record_label(potential_artist):
            return _clean_artist(potential_artist), _clean_title(remaining_title)
    
    # Couldn't extract - reject
    return artist, title


def _check_duplicate(artist: str, title: str, db_path: str = "lyra_registry.db") -> Optional[str]:
    """Check if track already exists in library.
    
    Returns:
        Filepath of existing track if duplicate, None if OK
    """
    import sqlite3
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT filepath, artist, title FROM tracks 
            WHERE status = 'active'
        """)
        
        artist_clean = _clean_string(artist)
        title_clean = _clean_string(_clean_title(title))
        
        for filepath, db_artist, db_title in cursor.fetchall():
            db_artist_clean = _clean_string(db_artist or "")
            db_title_clean = _clean_string(_clean_title(db_title or ""))
            
            # Fuzzy match
            artist_sim = _similarity(artist_clean, db_artist_clean)
            title_sim = _similarity(title_clean, db_title_clean)
            
            if artist_sim > 0.85 and title_sim > 0.85:
                conn.close()
                return filepath
        
        conn.close()
        return None
        
    except Exception as e:
        logger.warning(f"Duplicate check failed: {e}")
        return None


def _validate_musicbrainz(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Validate track exists in MusicBrainz."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    try:
        headers = {
            "User-Agent": "LyraOracle/1.0 (https://github.com/lyraoracle; contact@lyraoracle.dev)",
        }

        session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))

        resp = session.get(
            "https://musicbrainz.org/ws/2/recording",
            params={
                "query": f'artist:"{artist}" AND recording:"{title}"',
                "fmt": "json",
                "limit": 3,
            },
            headers=headers,
            timeout=(5, 8),  # (connect_timeout, read_timeout)
        )
        
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        recordings = data.get("recordings", [])
        
        if not recordings:
            return None
        
        # Find best match
        for rec in recordings:
            rec_title = rec.get("title", "")
            title_sim = _similarity(title, rec_title)
            
            if title_sim < 0.6:
                continue
            
            artists = rec.get("artist-credit", [])
            if not artists:
                continue
            
            rec_artist = artists[0].get("name", "")
            artist_sim = _similarity(artist, rec_artist)
            
            if artist_sim < 0.6:
                continue
            
            # Get release info
            releases = rec.get("releases", [])
            album = releases[0].get("title") if releases else None
            year = None
            if releases and releases[0].get("date"):
                year_match = re.match(r"(\d{4})", releases[0]["date"])
                if year_match:
                    year = int(year_match.group(1))
            
            return {
                "artist": rec_artist,
                "title": rec_title,
                "album": album,
                "year": year,
                "mb_id": rec.get("id"),
                "confidence": (title_sim + artist_sim) / 2,
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"MusicBrainz lookup failed: {e}")
        return None


# =============================================================================
# LAST.FM CONFIDENCE BOOST
# =============================================================================

def _lastfm_confidence_boost(artist: str, title: str, base_confidence: float) -> float:
    """Boost borderline MusicBrainz confidence using Last.fm listener counts.

    If a track has significant Last.fm listeners (>100), it's likely a real
    track even if the MusicBrainz fuzzy match was weak. Adds up to +0.15
    to the base confidence, scaled by listener count.

    Args:
        artist: Artist name.
        title: Track title.
        base_confidence: MusicBrainz confidence score (0-1).

    Returns:
        Boosted confidence (capped at base + 0.15).
    """
    try:
        from oracle.enrichers.lastfm import track_get_info

        payload = track_get_info(artist, title)
        track_node = payload.get("track", {}) if isinstance(payload, dict) else {}
        listeners_raw = track_node.get("listeners")
        if not listeners_raw:
            return base_confidence

        listeners = int(listeners_raw)
        if listeners < 100:
            return base_confidence

        # Scale boost: 100 listeners -> +0.05, 1000+ -> +0.10, 10000+ -> +0.15
        import math
        # log10(100)=2, log10(1000)=3, log10(10000)=4
        log_listeners = math.log10(max(listeners, 1))
        boost = min(0.15, max(0.0, (log_listeners - 2.0) * 0.075))
        return min(1.0, base_confidence + boost)
    except Exception as exc:
        logger.debug("Last.fm confidence boost failed: %s", exc)
        return base_confidence


# =============================================================================
# MAIN GUARD FUNCTION
# =============================================================================

def guard_acquisition(
    artist: str,
    title: str,
    album: Optional[str] = None,
    filepath: Optional[Path] = None,
    skip_validation: bool = False,
    skip_duplicate_check: bool = False,
    min_confidence: float = 0.6,
    lastfm_boost: bool = False,
) -> GuardResult:
    """Main guard function - check if track should be allowed into library.
    
    Args:
        artist: Claimed artist name
        title: Claimed track title
        album: Claimed album (optional)
        filepath: Path to audio file (for quality check)
        skip_validation: Skip MusicBrainz/Discogs validation
        skip_duplicate_check: Skip duplicate detection
        min_confidence: Minimum confidence for validation (0-1)
    
    Returns:
        GuardResult with allowed=True/False and cleaned metadata
    """
    warnings: List[str] = []
    
    # Step 1: Clean inputs
    artist_clean = _clean_artist(artist)
    title_clean = _clean_title(title)
    
    # Step 2: Try to extract real artist if needed
    artist_clean, title_clean = _extract_real_artist_from_title(artist_clean, title_clean)
    
    # Step 3: Check for junk
    junk_result = _check_junk(artist_clean, title_clean)
    if junk_result:
        return GuardResult(
            allowed=False,
            confidence=0.0,
            artist=artist_clean,
            title=title_clean,
            rejection_reason=junk_result[0],
            rejection_category=junk_result[1],
        )
    
    # Step 4: Check for record label as artist
    label_result = _check_record_label(artist_clean)
    if label_result:
        return GuardResult(
            allowed=False,
            confidence=0.0,
            artist=artist_clean,
            title=title_clean,
            rejection_reason=label_result[0],
            rejection_category=label_result[1],
        )
    
    # Step 5: Check for duplicates
    if not skip_duplicate_check:
        existing = _check_duplicate(artist_clean, title_clean)
        if existing:
            return GuardResult(
                allowed=False,
                confidence=1.0,
                artist=artist_clean,
                title=title_clean,
                rejection_reason=f"Duplicate of: {existing}",
                rejection_category="duplicate",
                is_duplicate=True,
                existing_path=existing,
            )
    
    # Step 6: Validate against MusicBrainz
    validated = None
    if not skip_validation:
        validated = _validate_musicbrainz(artist_clean, title_clean)
        
        if validated and validated.get("confidence", 0) >= min_confidence:
            # Use canonical metadata from MusicBrainz
            return GuardResult(
                allowed=True,
                confidence=validated["confidence"],
                artist=validated.get("artist", artist_clean),
                title=validated.get("title", title_clean),
                album=validated.get("album") or album,
                year=validated.get("year"),
                validated_by="musicbrainz",
                external_id=validated.get("mb_id"),
                warnings=warnings,
            )
        elif validated:
            # Low confidence match -- try Last.fm boost if enabled
            mb_conf = validated.get("confidence", 0)
            warnings.append(f"Low confidence MusicBrainz match: {mb_conf:.2f}")

            if lastfm_boost and 0.3 <= mb_conf < min_confidence:
                boosted = _lastfm_confidence_boost(artist_clean, title_clean, mb_conf)
                if boosted >= min_confidence:
                    warnings.append(f"Last.fm boosted confidence: {mb_conf:.2f} -> {boosted:.2f}")
                    return GuardResult(
                        allowed=True,
                        confidence=boosted,
                        artist=validated.get("artist", artist_clean),
                        title=validated.get("title", title_clean),
                        album=validated.get("album") or album,
                        year=validated.get("year"),
                        validated_by="musicbrainz+lastfm",
                        external_id=validated.get("mb_id"),
                        warnings=warnings,
                    )

    # Step 7: If no validation or low confidence, still allow but warn
    if skip_validation:
        return GuardResult(
            allowed=True,
            confidence=0.5,  # Unknown confidence
            artist=artist_clean,
            title=title_clean,
            album=album,
            validated_by="none",
            warnings=["Validation skipped - metadata not verified"],
        )
    
    # Step 8: No validation match - allow with warning
    return GuardResult(
        allowed=True,
        confidence=0.3,
        artist=artist_clean,
        title=title_clean,
        album=album,
        validated_by="none",
        warnings=["Could not validate against MusicBrainz - metadata may be incorrect"],
    )


def guard_file(filepath: Path) -> GuardResult:
    """Guard check for an existing file (extract metadata and validate).
    
    Useful for checking files already in downloads folder.
    """
    import mutagen
    
    if not filepath.exists():
        return GuardResult(
            allowed=False,
            confidence=0.0,
            rejection_reason=f"File not found: {filepath}",
            rejection_category="invalid",
        )
    
    # Try to extract metadata from file
    try:
        audio = mutagen.File(str(filepath), easy=True)
        if audio:
            artist = audio.get("artist", [""])[0] if audio.get("artist") else ""
            title = audio.get("title", [""])[0] if audio.get("title") else ""
            album = audio.get("album", [""])[0] if audio.get("album") else None
            
            if artist and title:
                return guard_acquisition(artist, title, album, filepath)
    except Exception:
        pass
    
    # Fall back to filename parsing
    stem = filepath.stem
    
    # Try "Artist - Title" format
    if " - " in stem:
        parts = stem.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip() if len(parts) > 1 else ""
        return guard_acquisition(artist, title, filepath=filepath)
    
    # Can't parse
    return GuardResult(
        allowed=False,
        confidence=0.0,
        rejection_reason=f"Could not parse metadata from: {filepath.name}",
        rejection_category="invalid",
    )


# =============================================================================
# BATCH OPERATIONS
# =============================================================================

def guard_downloads_folder(
    downloads_path: Path,
    extensions: Set[str] = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus"},
) -> List[Tuple[Path, GuardResult]]:
    """Check all files in downloads folder.
    
    Returns:
        List of (filepath, GuardResult) tuples
    """
    results = []
    
    for filepath in downloads_path.iterdir():
        if filepath.is_file() and filepath.suffix.lower() in extensions:
            result = guard_file(filepath)
            results.append((filepath, result))
    
    return results


def print_guard_summary(results: List[Tuple[Path, GuardResult]]) -> None:
    """Print summary of guard results."""
    allowed = [r for r in results if r[1].allowed]
    rejected = [r for r in results if not r[1].allowed]
    
    print(f"\n{'='*60}")
    print("ACQUISITION GUARD SUMMARY")
    print(f"{'='*60}")
    print(f"Total files: {len(results)}")
    print(f"Allowed: {len(allowed)}")
    print(f"Rejected: {len(rejected)}")
    
    if rejected:
        print(f"\nâŒ REJECTED ({len(rejected)}):")
        # Group by category
        by_category: Dict[str, List] = {}
        for filepath, result in rejected:
            cat = result.rejection_category or "unknown"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((filepath, result))
        
        for category, items in by_category.items():
            print(f"\n  [{category.upper()}] ({len(items)} files)")
            for filepath, result in items[:5]:
                print(f"    â€¢ {filepath.name[:50]}")
                print(f"      Reason: {result.rejection_reason[:60]}")
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more")
    
    if allowed:
        print(f"\nâœ… ALLOWED ({len(allowed)}):")
        for filepath, result in allowed[:10]:
            conf = f"{result.confidence:.0%}"
            validated = result.validated_by or "none"
            print(f"  â€¢ {result.artist[:25]:25s} - {result.title[:30]:30s} ({conf}, {validated})")
            if result.warnings:
                for w in result.warnings:
                    print(f"    âš ï¸ {w}")
        if len(allowed) > 10:
            print(f"  ... and {len(allowed) - 10} more")


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        # Test single file or folder
        path = Path(sys.argv[1])
        
        if path.is_dir():
            results = guard_downloads_folder(path)
            print_guard_summary(results)
        elif path.is_file():
            result = guard_file(path)
            print(f"\nFile: {path.name}")
            print(f"Allowed: {result.allowed}")
            print(f"Confidence: {result.confidence:.0%}")
            print(f"Artist: {result.artist}")
            print(f"Title: {result.title}")
            if result.rejection_reason:
                print(f"Rejection: {result.rejection_reason}")
            if result.warnings:
                print(f"Warnings: {result.warnings}")
        else:
            print(f"Path not found: {path}")
    else:
        # Interactive test
        print("Acquisition Guard - Interactive Test")
        print("Enter 'Artist - Title' to test, or 'q' to quit\n")
        
        while True:
            line = input("> ").strip()
            if line.lower() == 'q':
                break
            
            if " - " in line:
                parts = line.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()
            else:
                artist = line
                title = input("Title: ").strip()
            
            result = guard_acquisition(artist, title)
            
            status = "âœ… ALLOWED" if result.allowed else "âŒ REJECTED"
            print(f"\n{status}")
            print(f"  Confidence: {result.confidence:.0%}")
            print(f"  Artist: {result.artist}")
            print(f"  Title: {result.title}")
            if result.rejection_reason:
                print(f"  Reason: {result.rejection_reason}")
            if result.validated_by:
                print(f"  Validated by: {result.validated_by}")
            if result.warnings:
                for w in result.warnings:
                    print(f"  âš ï¸ {w}")
            print()
