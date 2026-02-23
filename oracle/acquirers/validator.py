"""Smart Acquisition Validator - Verify and clean metadata before accepting tracks.

Uses Discogs, MusicBrainz, and AcoustID to:
1. Verify artist/title are real
2. Get canonical metadata
3. Fingerprint match to confirm identity
4. Reject garbage (karaoke, wrong artist, etc.)
"""

from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv
from oracle.runtime_state import wait_if_paused
from oracle.db.schema import get_connection

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# API Keys
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
ACOUSTID_KEY = os.getenv("ACOUSTID_API_KEY")
MB_APP_NAME = os.getenv("MB_APP_NAME", "LyraOracle")
MB_VERSION = os.getenv("MB_APP_VERSION", "1.0")
MB_CONTACT = os.getenv("MB_CONTACT", "lyra@example.com")

# User agent for MusicBrainz
MB_USER_AGENT = f"{MB_APP_NAME}/{MB_VERSION} ({MB_CONTACT})"

# Junk patterns to reject
JUNK_PATTERNS = [
    r'\bkaraoke\b', r'\btribute\b', r'\bcover\b', r'\binstrumental\b',
    r'\b8[- ]?bit\b', r'\bremade\b', r'\bmidi\b', r'\bringtone\b',
    r'\bparty tyme\b', r'\bprosource\b', r'\bzzang\b',
    r'\bpiano version\b', r'\blullaby\b', r'\bmusic box\b',
]

# Record labels often mistaken as artists
RECORD_LABELS = {
    "epitaph records", "vagrant records", "rise records", "fueled by ramen",
    "hopeless records", "victory records", "fearless records", "dine alone records",
    "equal vision", "tooth & nail", "solid state", "roadrunner records",
    "interscope", "atlantic records", "columbia records", "riserecords",
    "lyrical lemonade", "worldstarhiphop", "colors show", "genius",
}


@dataclass
class ValidationResult:
    """Result of track validation."""
    valid: bool
    confidence: float  # 0.0 - 1.0
    canonical_artist: Optional[str] = None
    canonical_title: Optional[str] = None
    canonical_album: Optional[str] = None
    year: Optional[int] = None
    genres: List[str] = field(default_factory=list)
    isrc: Optional[str] = None
    discogs_id: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    source: str = "unknown"  # discogs, musicbrainz, acoustid


def similarity(a: str, b: str) -> float:
    """Calculate string similarity (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def clean_title(title: str) -> str:
    """Remove YouTube/video cruft from title."""
    if not title:
        return ""
    
    # Remove common video markers
    patterns = [
        r'\s*[\(\[]official\s*(video|audio|music video|lyric video|visualizer)[\)\]]',
        r'\s*[\(\[]explicit[\)\]]',
        r'\s*[\(\[]hd\s*\d*p?[\)\]]',
        r'\s*[\(\[]lyrics?[\)\]]',
        r'\s*[\(\[]audio[\)\]]',
        r'\s*[\(\[].*?version[\)\]]',
        r'\s*[\(\[]feat\.?.*?[\)\]]',  # Move features to separate field
        r'\s*-\s*(official|video|audio|lyric|hd|4k).*$',
        r'\s*\|\s*.*$',  # Remove " | Channel Name"
        r'\[.*?\]$',  # Remove trailing [anything]
    ]
    
    result = title
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    return result.strip()


def clean_artist(artist: str) -> str:
    """Clean up artist name."""
    if not artist:
        return ""
    
    # Remove "VEVO" suffix
    result = re.sub(r'\s*VEVO$', '', artist, flags=re.IGNORECASE)
    
    # Remove "- Topic" suffix (YouTube Music)
    result = re.sub(r'\s*-\s*Topic$', '', result, flags=re.IGNORECASE)
    
    # Fix common issues
    result = result.replace(' & ', ' and ').replace('  ', ' ')
    
    return result.strip()


def extract_artist_from_title(title: str) -> Tuple[Optional[str], str]:
    """Extract artist from 'Artist - Title' format."""
    if ' - ' in title:
        parts = title.split(' - ', 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return None, title


def is_junk(artist: str, title: str) -> Optional[str]:
    """Check if track is junk (karaoke, tribute, etc.)."""
    combined = f"{artist} {title}".lower()
    
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return f"Matches junk pattern: {pattern}"
    
    if artist.lower().strip() in RECORD_LABELS:
        return f"Artist is a record label: {artist}"
    
    return None


def search_discogs(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Search Discogs for track info."""
    if not DISCOGS_TOKEN:
        return None
    
    try:
        headers = {
            "Authorization": f"Discogs token={DISCOGS_TOKEN}",
            "User-Agent": MB_USER_AGENT,
        }
        
        # Search for release
        resp = requests.get(
            "https://api.discogs.com/database/search",
            params={
                "q": f"{artist} {title}",
                "type": "release",
                "per_page": 5,
            },
            headers=headers,
            timeout=10,
        )
        
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        results = data.get("results", [])
        
        if not results:
            return None
        
        # Find best match
        for result in results:
            result_title = result.get("title", "")
            # Discogs format: "Artist - Album"
            if " - " in result_title:
                parts = result_title.split(" - ", 1)
                result_artist = parts[0]
                result_album = parts[1] if len(parts) > 1 else ""
                
                artist_sim = similarity(artist, result_artist)
                if artist_sim > 0.7:
                    return {
                        "artist": result_artist,
                        "album": result_album,
                        "year": result.get("year"),
                        "genres": result.get("genre", []),
                        "styles": result.get("style", []),
                        "discogs_id": str(result.get("id")),
                        "confidence": artist_sim,
                    }
        
        return None
        
    except Exception as e:
        logger.warning(f"Discogs search failed: {e}")
        return None


def search_musicbrainz(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Search MusicBrainz for track info."""
    try:
        headers = {"User-Agent": MB_USER_AGENT}
        
        # Search for recording
        resp = requests.get(
            "https://musicbrainz.org/ws/2/recording",
            params={
                "query": f'artist:"{artist}" AND recording:"{title}"',
                "fmt": "json",
                "limit": 5,
            },
            headers=headers,
            timeout=10,
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
            title_sim = similarity(title, rec_title)
            
            if title_sim < 0.7:
                continue
            
            # Get artist
            artists = rec.get("artist-credit", [])
            if not artists:
                continue
            
            rec_artist = artists[0].get("name", "") if artists else ""
            artist_sim = similarity(artist, rec_artist)
            
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
            
            # Get ISRC
            isrcs = rec.get("isrcs", [])
            isrc = isrcs[0] if isrcs else None
            
            return {
                "artist": rec_artist,
                "title": rec_title,
                "album": album,
                "year": year,
                "isrc": isrc,
                "musicbrainz_id": rec.get("id"),
                "confidence": (title_sim + artist_sim) / 2,
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"MusicBrainz search failed: {e}")
        return None


def search_itunes(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Search iTunes public catalog as a backup to MusicBrainz/Discogs."""
    try:
        resp = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{artist} {title}",
                "media": "music",
                "entity": "song",
                "limit": 10,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        best: Optional[Dict[str, Any]] = None
        best_conf = 0.0
        for item in results:
            cand_artist = str(item.get("artistName", "")).strip()
            cand_title = str(item.get("trackName", "")).strip()
            if not cand_artist or not cand_title:
                continue

            artist_sim = similarity(artist, cand_artist)
            title_sim = similarity(title, cand_title)
            confidence = (artist_sim + title_sim) / 2.0
            if confidence > best_conf:
                year = None
                release_date = str(item.get("releaseDate", ""))
                year_match = re.match(r"(\d{4})", release_date)
                if year_match:
                    year = int(year_match.group(1))

                best_conf = confidence
                best = {
                    "artist": cand_artist,
                    "title": cand_title,
                    "album": item.get("collectionName"),
                    "year": year,
                    "isrc": item.get("isrc"),
                    "confidence": confidence,
                }
        return best
    except Exception as e:
        logger.warning(f"iTunes search failed: {e}")
        return None


def validate_track(
    artist: str,
    title: str,
    filepath: Optional[Path] = None,
    min_confidence: float = 0.7,
) -> ValidationResult:
    """Validate and enrich track metadata.
    
    Args:
        artist: Claimed artist name
        title: Claimed track title
        filepath: Path to audio file (for fingerprinting)
        min_confidence: Minimum confidence to accept (0-1)
    
    Returns:
        ValidationResult with canonical metadata or rejection reason
    """
    # Clean inputs
    artist = clean_artist(artist)
    title = clean_title(title)
    
    # Handle "Artist - Title" in title field
    if not artist or artist.lower() in RECORD_LABELS:
        extracted_artist, extracted_title = extract_artist_from_title(title)
        if extracted_artist:
            artist = clean_artist(extracted_artist)
            title = clean_title(extracted_title)
    
    # Check for junk
    junk_reason = is_junk(artist, title)
    if junk_reason:
        return ValidationResult(
            valid=False,
            confidence=0.0,
            rejection_reason=junk_reason,
        )
    
    # Try MusicBrainz first (more structured data)
    mb_result = search_musicbrainz(artist, title)
    if mb_result and mb_result.get("confidence", 0) >= min_confidence:
        return ValidationResult(
            valid=True,
            confidence=mb_result["confidence"],
            canonical_artist=mb_result.get("artist"),
            canonical_title=mb_result.get("title"),
            canonical_album=mb_result.get("album"),
            year=mb_result.get("year"),
            isrc=mb_result.get("isrc"),
            musicbrainz_id=mb_result.get("musicbrainz_id"),
            source="musicbrainz",
        )
    
    time.sleep(0.5)  # Rate limit
    
    # Try Discogs
    discogs_result = search_discogs(artist, title)
    if discogs_result and discogs_result.get("confidence", 0) >= min_confidence:
        genres = discogs_result.get("genres", []) + discogs_result.get("styles", [])
        return ValidationResult(
            valid=True,
            confidence=discogs_result["confidence"],
            canonical_artist=discogs_result.get("artist"),
            canonical_album=discogs_result.get("album"),
            year=discogs_result.get("year"),
            genres=genres[:5],
            discogs_id=discogs_result.get("discogs_id"),
            source="discogs",
        )

    # Backup provider beyond MusicBrainz/Discogs.
    itunes_result = search_itunes(artist, title)
    if itunes_result and itunes_result.get("confidence", 0) >= min_confidence:
        return ValidationResult(
            valid=True,
            confidence=itunes_result["confidence"],
            canonical_artist=itunes_result.get("artist"),
            canonical_title=itunes_result.get("title"),
            canonical_album=itunes_result.get("album"),
            year=itunes_result.get("year"),
            isrc=itunes_result.get("isrc"),
            source="itunes",
        )
    
    # If we have partial matches, return with lower confidence
    best_confidence = max(
        mb_result.get("confidence", 0) if mb_result else 0,
        discogs_result.get("confidence", 0) if discogs_result else 0,
        itunes_result.get("confidence", 0) if itunes_result else 0,
    )
    
    if best_confidence > 0.5:
        # Partial match - use best data available
        candidates = [r for r in (mb_result, discogs_result, itunes_result) if r]
        best = max(candidates, key=lambda r: r.get("confidence", 0)) if candidates else None
        return ValidationResult(
            valid=True,
            confidence=best_confidence,
            canonical_artist=best.get("artist") if best else artist,
            canonical_title=best.get("title") if best else title,
            canonical_album=best.get("album") if best else None,
            year=best.get("year") if best else None,
            source="partial_match",
        )
    
    # No match found
    return ValidationResult(
        valid=False,
        confidence=0.0,
        rejection_reason=f"Could not verify: {artist} - {title}",
    )


def validate_and_fix_library(
    limit: int = 0,
    apply: bool = True,
    min_confidence: float = 0.7,
    workers: int = 0,
    only_unvalidated: bool = True,
    full_rescan_if_needed: bool = True,
) -> Dict[str, int]:
    """Validate tracks and optionally write fixes + white-glove markers."""

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    _ensure_white_glove_table(cursor)
    conn.commit()

    if only_unvalidated:
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE status='active'")
        total_active = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM track_validation WHERE status='valid'")
        total_white_gloved = int(cursor.fetchone()[0] or 0)
        do_full_scan = bool(full_rescan_if_needed and total_active > 0 and total_white_gloved == 0)
    else:
        do_full_scan = True

    sql = "SELECT track_id, artist, title, album, year, genre, filepath FROM tracks WHERE status='active'"
    params: Tuple[Any, ...] = ()
    if only_unvalidated and not do_full_scan:
        sql += (
            " AND track_id NOT IN (SELECT track_id FROM track_validation WHERE status='valid')"
        )
    sql += " ORDER BY artist, title"
    if limit and int(limit) > 0:
        sql += " LIMIT ?"
        params = (int(limit),)
    cursor.execute(sql, params)
    tracks = cursor.fetchall()

    mode = "full white-glove baseline" if do_full_scan else ("only unvalidated tracks" if only_unvalidated else "full scan")
    print(f"Validating {len(tracks)} tracks ({mode})...\n")
    stats = {"validated": 0, "fixed": 0, "failed": 0, "skipped": 0, "would_fix": 0}
    work_items: List[Tuple[Any, ...]] = list(tracks)

    if workers <= 0:
        from oracle.perf import auto_workers
        workers = auto_workers("network")
    workers = max(1, min(int(workers), 32))
    print(f"Validation workers: {workers}")

    def _validate_row(row: Tuple[Any, ...]) -> Tuple[Tuple[Any, ...], ValidationResult]:
        wait_if_paused("validate")
        _, artist, title, _, _, _, filepath = row
        result = validate_track(
            artist,
            title,
            Path(filepath) if filepath else None,
            min_confidence=min_confidence,
        )
        return row, result

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_validate_row, row) for row in work_items]
        for fut in as_completed(futures):
            (track_id, artist, title, album, year, genre, _), result = fut.result()
            completed += 1
            print(f"[{completed}/{len(work_items)}] {artist[:25]:25s} - {title[:35]:35s}", end=" ")

            if result.valid and result.confidence >= min_confidence:
                updates = []
                update_params = []

                if result.canonical_artist and result.canonical_artist != artist:
                    updates.append("artist = ?")
                    update_params.append(result.canonical_artist)

                if result.canonical_album and not album:
                    updates.append("album = ?")
                    update_params.append(result.canonical_album)

                if result.year and not year:
                    updates.append("year = ?")
                    update_params.append(str(result.year))

                if result.genres and not genre:
                    updates.append("genre = ?")
                    update_params.append(", ".join(result.genres[:3]))

                if updates:
                    if apply:
                        update_params.append(track_id)
                        cursor.execute(
                            f"UPDATE tracks SET {', '.join(updates)} WHERE track_id = ?",
                            update_params,
                        )
                        _mark_white_gloved(
                            cursor,
                            track_id=track_id,
                            confidence=float(result.confidence),
                            source=result.source,
                        )
                        print(f"-> fixed ({result.source})")
                        stats["fixed"] += 1
                    else:
                        print(f"-> would fix ({result.source})")
                        stats["would_fix"] += 1
                else:
                    if apply:
                        _mark_white_gloved(
                            cursor,
                            track_id=track_id,
                            confidence=float(result.confidence),
                            source=result.source,
                        )
                    print("-> valid")
                    stats["validated"] += 1
            else:
                reason = result.rejection_reason or "low confidence"
                print(f"-> failed: {reason[:40]}")
                stats["failed"] += 1

            if completed % 25 == 0:
                if apply:
                    conn.commit()
                print(f"\n  Checkpoint: {stats}\n")

    if apply:
        conn.commit()
    conn.close()

    print("\n=== Complete ===")
    print(f"Validated: {stats['validated']}")
    print(f"Fixed: {stats['fixed']}")
    print(f"Would fix: {stats['would_fix']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped (already complete): {stats['skipped']}")
    return stats


def _ensure_white_glove_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS track_validation (
            track_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            confidence REAL,
            source TEXT,
            validated_at REAL NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_validation_status ON track_validation(status)"
    )


def _mark_white_gloved(cursor, *, track_id: str, confidence: float, source: str) -> None:
    cursor.execute(
        """
        INSERT INTO track_validation (track_id, status, confidence, source, validated_at)
        VALUES (?, 'valid', ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            status=excluded.status,
            confidence=excluded.confidence,
            source=excluded.source,
            validated_at=excluded.validated_at
        """,
        (track_id, confidence, source, time.time()),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    validate_and_fix_library()

