"""MusicBrainz metadata provider — hardened with compliant rate-limiting.

Architecture constraints:
    - Enforced 1.1s minimum interval between requests (MB rate limit)
    - Exponential backoff with jitter on retryable errors (429, 5xx)
    - Respects Retry-After header from server
    - Compliant User-Agent: ``AppName/Version (contact)``
    - Thread-safe rate limiter via threading.Lock
    - MBID-based lookups preferred over text search
    - Artist whitelist validation: if MB returns a valid Artist ID,
      the entity bypasses all junk filters downstream

Env vars:
    MB_BASE_URL          — API base (default: https://musicbrainz.org/ws/2)
    MB_TIMEOUT_SECONDS   — Request timeout (default: 30)
    MB_MAX_RETRIES       — Max retry attempts (default: 4)
    MB_MIN_INTERVAL_SECONDS — Min seconds between requests (default: 1.1)
    MB_RATE_LIMIT_RPS    — Legacy: requests per second (default: 0.9)
    MB_APP_NAME          — User-Agent app name (default: LyraOracle)
    MB_APP_VERSION       — User-Agent version (default: 1.0)
    MB_CONTACT           — User-Agent contact email
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MB_BASE_URL = os.getenv("MB_BASE_URL", "https://musicbrainz.org/ws/2")
_REQUEST_TIMEOUT = float(os.getenv("MB_TIMEOUT_SECONDS", "30"))
_MAX_RETRIES = int(os.getenv("MB_MAX_RETRIES", "4"))
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Thread-safe rate limiter.
# NOTE: keep `_LAST_REQUEST_TS` as the public module symbol for test monkeypatch
# compatibility.
_rate_lock = threading.Lock()
_LAST_REQUEST_TS = 0.0

# Persistent session for connection pooling
_SESSION = requests.Session()


def _user_agent() -> str:
    name = os.getenv("MB_APP_NAME", "LyraOracle")
    version = os.getenv("MB_APP_VERSION", "1.0")
    contact = os.getenv("MB_CONTACT", "lyra@oracle.local")
    return f"{name}/{version} ({contact})"


def _min_interval() -> float:
    """Minimum seconds between requests. Default 1.1s (compliant)."""
    val = os.getenv("MB_MIN_INTERVAL_SECONDS")
    if val:
        try:
            return max(0.5, float(val))
        except ValueError:
            pass

    rps = os.getenv("MB_RATE_LIMIT_RPS", "0.9")
    try:
        rate = max(0.1, float(rps))
    except ValueError:
        rate = 0.9
    return 1.0 / rate


# ---------------------------------------------------------------------------
# Rate limiter + request engine
# ---------------------------------------------------------------------------

def _respect_rate_limit() -> None:
    """Enforce minimum interval between MB requests (thread-safe)."""
    global _LAST_REQUEST_TS
    with _rate_lock:
        interval = _min_interval()
        elapsed = time.monotonic() - _LAST_REQUEST_TS
        wait = max(0.0, interval - elapsed)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_TS = time.monotonic()


def _retry_after(response: requests.Response) -> float:
    """Extract Retry-After header value in seconds."""
    raw = response.headers.get("Retry-After", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 0.0


def _request(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    """Execute a rate-limited, retrying GET against MusicBrainz.

    Implements:
        - 1.1s enforced sleep between requests
        - Exponential backoff with jitter on 429/5xx
        - Retry-After header respected
        - Compliant User-Agent
    """
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    params.setdefault("fmt", "json")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _respect_rate_limit()
            response = _SESSION.get(
                url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT,
            )

            if response.status_code in _RETRYABLE_STATUS:
                server_wait = _retry_after(response)
                # Exponential backoff with jitter
                base_backoff = min(16.0, 2 ** (attempt - 1))
                jitter = random.uniform(0, base_backoff * 0.3)
                wait = max(server_wait, base_backoff) + jitter
                logger.debug(
                    "MB %d on attempt %d/%d, waiting %.1fs",
                    response.status_code, attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 404:
                logger.debug("MB 404: %s", url)
                return {}

            response.raise_for_status()
            return response.json()

        except requests.ConnectionError as exc:
            logger.warning("MB connection error attempt %d: %s", attempt, exc)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(16.0, 2 ** attempt))

        except requests.Timeout:
            logger.warning("MB timeout attempt %d/%d", attempt, _MAX_RETRIES)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(8.0, 2 ** attempt))

        except requests.RequestException as exc:
            logger.warning("MB request error attempt %d: %s", attempt, exc)
            if attempt >= _MAX_RETRIES:
                return {}
            time.sleep(min(16.0, 2 ** (attempt - 1)))

    return {}


def _base() -> str:
    return MB_BASE_URL.rstrip("/")


# ---------------------------------------------------------------------------
# Recording search + lookup
# ---------------------------------------------------------------------------

def search_recording(
    artist: str,
    title: str,
    album: Optional[str] = None,
    duration: Optional[float] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Search for a recording by artist + title.

    Returns raw MB response with ``recordings`` list.
    """
    # Lucene-escape special characters in query values
    def _esc(s: str) -> str:
        return re.sub(r'([+\-&|!(){}[\]^"~*?:\\])', r"\\\1", s)

    query = f'recording:"{_esc(title)}" AND artist:"{_esc(artist)}"'
    if album:
        query += f' AND release:"{_esc(album)}"'

    params: Dict[str, str] = {"query": query, "limit": str(limit)}
    if duration:
        params["dur"] = str(int(duration * 1000))

    return _request(f"{_base()}/recording", params)


def get_recording_details(mbid: str) -> Dict[str, Any]:
    """Fetch full recording details by MBID.

    Includes: artists, releases (with release-groups), tags, ISRCs.
    """
    params = {"inc": "artists+releases+release-groups+tags+isrcs"}
    return _request(f"{_base()}/recording/{mbid}", params)


# ---------------------------------------------------------------------------
# Artist search + validation
# ---------------------------------------------------------------------------

def search_artist(name: str, limit: int = 5) -> Dict[str, Any]:
    """Search for an artist by name.

    Returns dict with ``artists`` list containing: id, name, type,
    disambiguation, score.
    """
    def _esc(s: str) -> str:
        return re.sub(r'([+\-&|!(){}[\]^"~*?:\\])', r"\\\1", s)

    params = {"query": f'artist:"{_esc(name)}"', "limit": str(limit)}
    return _request(f"{_base()}/artist", params)


def validate_artist(name: str, min_score: int = 80) -> Optional[Dict[str, Any]]:
    """Validate an artist name against MusicBrainz.

    If MB returns a match with score >= min_score and a valid Artist MBID,
    the artist is considered whitelisted and should bypass all junk filters.

    Args:
        name: Artist name to validate.
        min_score: Minimum MB search score (0-100) to consider valid.

    Returns:
        Dict with ``mbid``, ``name``, ``type``, ``score`` if valid, else None.
    """
    if not name or not name.strip():
        return None

    data = search_artist(name, limit=3)
    artists = data.get("artists", [])

    for artist in artists:
        score = int(artist.get("score", 0))
        mbid = artist.get("id")
        mb_name = artist.get("name", "")

        if score < min_score or not mbid:
            continue

        # Verify name similarity (word-boundary aware)
        name_sim = SequenceMatcher(
            None, name.lower().strip(), mb_name.lower().strip()
        ).ratio()

        if name_sim >= 0.80 or score >= 95:
            return {
                "mbid": mbid,
                "name": mb_name,
                "type": artist.get("type"),
                "disambiguation": artist.get("disambiguation"),
                "score": score,
            }

    return None


# ---------------------------------------------------------------------------
# Release / release-group lookups
# ---------------------------------------------------------------------------

def get_release_groups(
    artist_mbid: str,
    release_type: str = "album",
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get release groups (albums/EPs/singles) for an artist.

    Args:
        artist_mbid: MusicBrainz artist ID.
        release_type: One of album, ep, single.
        offset: Pagination offset.
        limit: Max results per page.

    Returns:
        Dict with ``release-groups`` list.
    """
    params = {
        "artist": artist_mbid,
        "type": release_type,
        "offset": str(offset),
        "limit": str(limit),
    }
    return _request(f"{_base()}/release-group", params)


def get_releases_for_group(release_group_mbid: str) -> Dict[str, Any]:
    """Get releases (with recordings/tracks) for a release group.

    Returns dict with ``releases`` list, each containing ``media`` with ``tracks``.
    """
    params = {
        "release-group": release_group_mbid,
        "inc": "recordings+artist-credits",
        "limit": "50",
    }
    return _request(f"{_base()}/release", params)


# ---------------------------------------------------------------------------
# High-level enrichment helpers
# ---------------------------------------------------------------------------

@dataclass
class RecordingMatch:
    """Structured result from a recording search or MBID lookup."""

    recording_mbid: Optional[str] = None
    artist: Optional[str] = None
    artist_mbid: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    isrc: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "musicbrainz"


def enrich_by_mbid(recording_mbid: str) -> Optional[RecordingMatch]:
    """Fetch canonical metadata for a known MusicBrainz Recording ID.

    This is the preferred path: fingerprint gives us an MBID, and we pull
    canonical data directly without fuzzy matching.
    """
    data = get_recording_details(recording_mbid)
    if not data or "error" in data:
        return None

    # Artist
    artist_credit = data.get("artist-credit", [])
    artist_parts = []
    artist_mbid = None
    for credit in artist_credit:
        a = credit.get("artist", {})
        artist_parts.append(credit.get("name", a.get("name", "")))
        if artist_mbid is None:
            artist_mbid = a.get("id")
        joinphrase = credit.get("joinphrase", "")
        if joinphrase:
            artist_parts.append(joinphrase)

    artist_name = "".join(artist_parts).strip()

    # Title
    title = data.get("title")

    # ISRCs
    isrcs = data.get("isrcs", [])
    isrc = isrcs[0] if isrcs else None

    # Tags
    tags = [t.get("name", "") for t in data.get("tags", []) if t.get("name")]

    # Album + year from first release
    album = None
    year = None
    track_number = None
    disc_number = None
    releases = data.get("releases", [])
    if releases:
        rel = releases[0]
        album = rel.get("title")
        date = rel.get("date", "")
        if date:
            year = str(date)[:4]

        # Release group info
        rg = rel.get("release-group", {})
        if rg and not album:
            album = rg.get("title")

        # Track/disc number from media
        for medium in rel.get("media", []):
            for track in medium.get("tracks", []):
                if track.get("recording", {}).get("id") == recording_mbid:
                    try:
                        track_number = int(track.get("number", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        disc_number = int(medium.get("position", 1))
                    except (ValueError, TypeError):
                        pass
                    break

    return RecordingMatch(
        recording_mbid=recording_mbid,
        artist=artist_name,
        artist_mbid=artist_mbid,
        title=title,
        album=album,
        year=year,
        track_number=track_number,
        disc_number=disc_number,
        isrc=isrc,
        tags=tags,
        confidence=1.0,
        source="musicbrainz_mbid",
    )


def enrich_by_text(
    artist: str,
    title: str,
    album: Optional[str] = None,
    duration: Optional[float] = None,
    min_similarity: float = 0.60,
) -> Optional[RecordingMatch]:
    """Fallback enrichment via text search when no MBID is available.

    Uses fuzzy matching to verify results. Requires both artist and title
    similarity >= min_similarity.

    Args:
        artist: Artist name.
        title: Track title.
        album: Album name (optional, used to narrow search).
        duration: Track duration in seconds (optional).
        min_similarity: Minimum SequenceMatcher ratio for match.

    Returns:
        RecordingMatch if a confident match is found, else None.
    """
    data = search_recording(artist, title, album, duration)
    recordings = data.get("recordings", [])

    if not recordings:
        return None

    best_match: Optional[RecordingMatch] = None
    best_score = 0.0

    for rec in recordings[:10]:
        rec_title = rec.get("title", "")
        rec_score = int(rec.get("score", 0))

        # Extract artist from artist-credit
        artist_credit = rec.get("artist-credit", [])
        rec_artist = "".join(
            c.get("name", c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
            for c in artist_credit
        ).strip()

        # Similarity check
        title_sim = SequenceMatcher(
            None, title.lower().strip(), rec_title.lower().strip()
        ).ratio()
        artist_sim = SequenceMatcher(
            None, artist.lower().strip(), rec_artist.lower().strip()
        ).ratio()

        if title_sim < min_similarity or artist_sim < min_similarity:
            continue

        # Combined score
        combined = (artist_sim * 0.4 + title_sim * 0.6) * (rec_score / 100)

        if combined > best_score:
            best_score = combined

            # Extract MBID
            rec_mbid = rec.get("id")
            artist_mbid = None
            if artist_credit:
                artist_mbid = artist_credit[0].get("artist", {}).get("id")

            # Album/year from releases
            rec_album = None
            rec_year = None
            releases = rec.get("releases", [])
            if releases:
                rec_album = releases[0].get("title")
                date = releases[0].get("date", "")
                if date:
                    rec_year = str(date)[:4]

            best_match = RecordingMatch(
                recording_mbid=rec_mbid,
                artist=rec_artist or artist,
                artist_mbid=artist_mbid,
                title=rec_title or title,
                album=rec_album or album,
                year=rec_year,
                confidence=combined,
                source="musicbrainz_text",
            )

    return best_match


# ---------------------------------------------------------------------------
# Collaboration splitting (conservative, boundary-aware)
# ---------------------------------------------------------------------------

def split_collaboration(
    artist_string: str,
    recording_mbid: Optional[str] = None,
) -> List[str]:
    """Split a collaboration string into individual artist names.

    Conservative logic:
        - Only splits on confirmed multi-artist credits from MusicBrainz
        - Does NOT split on \" x \" unless MB confirms multiple artists
          (prevents corrupting names like \"Brand X\", \"alt-J x Radiohead\")
        - Safe splits: feat., ft., featuring, with, &, and, vs.

    Args:
        artist_string: Raw artist string (e.g. \"Artist1 feat. Artist2\").
        recording_mbid: Optional MBID to verify against MB credits.

    Returns:
        List of individual artist names.
    """
    if not artist_string:
        return []

    # If we have an MBID, use MB's own artist-credit as ground truth
    if recording_mbid:
        data = get_recording_details(recording_mbid)
        credits = data.get("artist-credit", [])
        if len(credits) > 1:
            return [
                c.get("name", c.get("artist", {}).get("name", ""))
                for c in credits
                if c.get("name") or c.get("artist", {}).get("name")
            ]

    # Safe split patterns (conservative — never split on " x ")
    safe_patterns = [
        r"\s+feat\.?\s+",
        r"\s+ft\.?\s+",
        r"\s+featuring\s+",
        r"\s+with\s+",
        r"\s+vs\.?\s+",
    ]

    parts = [artist_string]
    for pattern in safe_patterns:
        new_parts = []
        for part in parts:
            splits = re.split(pattern, part, flags=re.IGNORECASE)
            new_parts.extend(s.strip() for s in splits if s.strip())
        parts = new_parts

    # Handle " & " and " and " only if result looks like two distinct names
    # (not part of a band name like "Florence and the Machine")
    ampersand_patterns = [r"\s+&\s+", r"\s+and\s+"]
    for pattern in ampersand_patterns:
        if len(parts) == 1:
            candidate_splits = re.split(pattern, parts[0], flags=re.IGNORECASE)
            if len(candidate_splits) == 2:
                # Only split if both parts are >= 3 chars and look like names
                a, b = candidate_splits[0].strip(), candidate_splits[1].strip()
                if (
                    len(a) >= 3
                    and len(b) >= 3
                    and not b.lower().startswith("the ")
                    and b[0].isupper()
                ):
                    parts = [a, b]

    return parts
