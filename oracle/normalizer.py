"""Metadata Normalizer — sanitized tag injection and library normalization.

Two responsibilities:
    1. **Database normalization**: Fix artist/title variations in lyra_registry.db
    2. **Tag injection**: Write verified metadata into audio file binary headers
       via mutagen (ID3v2.3 for MP3, Vorbis for FLAC, MP4 atoms for M4A)

System invariants:
    - ZERO destructive file operations — no os.remove(), no file deletion
    - Files with irresolvable metadata are flagged, never destroyed
    - Retains existing ReplayGain values during tag writes
    - Writes musicbrainz_recordingid into file tags for future-proofing
    - Plan -> Review -> Apply workflow: --dry-run is default
    - JSON audit log for every tag write operation
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TXXX, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical artist mapping (lowercase key -> proper case)
# ---------------------------------------------------------------------------

ARTIST_CANONICAL: Dict[str, str] = {
    "coheed and cambria": "Coheed and Cambria",
    "coheed & cambria": "Coheed and Cambria",
    "coheed, cambria": "Coheed and Cambria",
    "fall out boy": "Fall Out Boy",
    "fallout boy": "Fall Out Boy",
    "brand new": "Brand New",
    "taking back sunday": "Taking Back Sunday",
    "takingbacksunday": "Taking Back Sunday",
    "rise against": "Rise Against",
    "riseagainst": "Rise Against",
    "run the jewels": "Run the Jewels",
    "runthejewels": "Run the Jewels",
    "massive attack": "Massive Attack",
    "massiveattack": "Massive Attack",
    "tv on the radio": "TV on the Radio",
    "a day to remember": "A Day to Remember",
    "my chemical romance": "My Chemical Romance",
    "panic! at the disco": "Panic! at the Disco",
    "panic at the disco": "Panic! at the Disco",
    "twenty one pilots": "Twenty One Pilots",
    "twentyone pilots": "Twenty One Pilots",
    "21 pilots": "Twenty One Pilots",
    "blink-182": "blink-182",
    "blink 182": "blink-182",
    "system of a down": "System of a Down",
    "rage against the machine": "Rage Against the Machine",
    "red hot chili peppers": "Red Hot Chili Peppers",
    "rhcp": "Red Hot Chili Peppers",
    "foo fighters": "Foo Fighters",
    "the foo fighters": "Foo Fighters",
    "green day": "Green Day",
    "weezer": "Weezer",
    "linkin park": "Linkin Park",
    "deftones": "Deftones",
    "the deftones": "Deftones",
    "tool": "Tool",
    "radiohead": "Radiohead",
    "muse": "Muse",
    "arctic monkeys": "Arctic Monkeys",
    "the killers": "The Killers",
    "queens of the stone age": "Queens of the Stone Age",
    "qotsa": "Queens of the Stone Age",
    "kendrick lamar": "Kendrick Lamar",
    "j. cole": "J. Cole",
    "j cole": "J. Cole",
    "childish gambino": "Childish Gambino",
    "tyler, the creator": "Tyler, the Creator",
    "tyler the creator": "Tyler, the Creator",
    "denzel curry": "Denzel Curry",
    "jid": "JID",
    "alt-j": "alt-J",
    "alt j": "alt-J",
}

# Featured artist extraction patterns
FEAT_PATTERNS: List[str] = [
    r"\s*[\(\[]feat\.?\s+([^\)\]]+)[\)\]]",
    r"\s*[\(\[]ft\.?\s+([^\)\]]+)[\)\]]",
    r"\s*[\(\[]featuring\s+([^\)\]]+)[\)\]]",
    r"\s*[\(\[]with\s+([^\)\]]+)[\)\]]",
    r"\s+feat\.?\s+(.+?)(?:\s*[\(\[]|$)",
    r"\s+ft\.?\s+(.+?)(?:\s*[\(\[]|$)",
]

# Title cleanup patterns (YouTube/video cruft)
TITLE_CLEANUP_PATTERNS: List[str] = [
    r"\s*[\(\[]official\s*(music\s*)?(video|audio|lyric\s*video|visualizer)[\)\]]",
    r"\s*[\(\[]explicit[\)\]]",
    r"\s*[\(\[]clean[\)\]]",
    r"\s*[\(\[]hd\s*\d*p?[\)\]]",
    r"\s*[\(\[]4k[\)\]]",
    r"\s*[\(\[]lyrics?[\)\]]",
    r"\s*[\(\[]audio[\)\]]",
    r"\s*[\(\[]video[\)\]]",
    r"\s*-\s*official\s*(music\s*)?(video|audio).*$",
    r"\s*\|\s*[^|]+$",
]

# ReplayGain tags to preserve during tag injection
_REPLAYGAIN_TAGS = {
    # ID3
    "replaygain_track_gain", "replaygain_track_peak",
    "replaygain_album_gain", "replaygain_album_peak",
    # Vorbis / FLAC
    "REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_TRACK_PEAK",
    "REPLAYGAIN_ALBUM_GAIN", "REPLAYGAIN_ALBUM_PEAK",
    # MP4
    "----:com.apple.iTunes:replaygain_track_gain",
    "----:com.apple.iTunes:replaygain_track_peak",
    "----:com.apple.iTunes:replaygain_album_gain",
    "----:com.apple.iTunes:replaygain_album_peak",
}


# ---------------------------------------------------------------------------
# Tag write result
# ---------------------------------------------------------------------------

@dataclass
class TagWriteResult:
    """Result of a tag injection operation."""

    filepath: str
    success: bool
    action: str  # "write", "skip", "error"
    fields_written: List[str] = field(default_factory=list)
    fields_preserved: List[str] = field(default_factory=list)
    error: Optional[str] = None
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Database normalization functions
# ---------------------------------------------------------------------------

def normalize_artist(artist: str) -> Tuple[str, List[str]]:
    """Normalize artist name and extract featured artists.

    Returns:
        (primary_artist, [featured_artists])
    """
    if not artist:
        return "", []

    original = artist.strip()
    featured: List[str] = []

    # Canonical mapping first
    lookup = original.lower().strip()
    if lookup in ARTIST_CANONICAL:
        return ARTIST_CANONICAL[lookup], []

    # Extract featured artists
    for pattern in FEAT_PATTERNS:
        match = re.search(pattern, original, re.IGNORECASE)
        if match:
            feat_artist = match.group(1).strip()
            featured.append(feat_artist)
            original = re.sub(pattern, "", original, flags=re.IGNORECASE).strip()

    # Check canonical again after cleanup
    lookup = original.lower().strip()
    if lookup in ARTIST_CANONICAL:
        return ARTIST_CANONICAL[lookup], featured

    # Title case if all lowercase or all uppercase
    if original.islower() or original.isupper():
        original = original.title()

    return original.strip(), featured


def normalize_title(title: str) -> Tuple[str, List[str]]:
    """Clean up track title and extract featured artists.

    Returns:
        (clean_title, [featured_artists])
    """
    if not title:
        return "", []

    original = title.strip()
    featured: List[str] = []

    # Extract featured artists from title
    for pattern in FEAT_PATTERNS:
        match = re.search(pattern, original, re.IGNORECASE)
        if match:
            feat_artist = match.group(1).strip()
            featured.append(feat_artist)
            original = re.sub(pattern, "", original, flags=re.IGNORECASE).strip()

    # Remove YouTube/video cruft
    for pattern in TITLE_CLEANUP_PATTERNS:
        original = re.sub(pattern, "", original, flags=re.IGNORECASE).strip()

    # Remove duplicate artist prefix ("Artist - Artist - Song" -> "Song")
    parts = original.split(" - ")
    if len(parts) >= 3 and parts[0].lower().strip() == parts[1].lower().strip():
        original = " - ".join(parts[2:])

    # Clean up whitespace
    original = re.sub(r"\s+", " ", original).strip()

    return original, featured


def extract_artist_from_title(title: str) -> Tuple[Optional[str], str]:
    """Extract artist from 'Artist - Title' format.

    Uses word-boundary matching — does NOT use substring checks that
    would false-positive on artist names containing common words.

    Returns:
        (artist or None, remaining_title)
    """
    if " - " not in title:
        return None, title

    parts = title.split(" - ", 1)
    potential_artist = parts[0].strip()
    remaining = parts[1].strip() if len(parts) > 1 else ""

    if len(potential_artist) < 2:
        return None, title

    # Word-boundary check for label indicators (not substring!)
    label_patterns = [
        r"\bofficial\b", r"\bvevo\b", r"\brecords\b",
        r"\btopic\b", r"\bchannel\b",
    ]
    for pattern in label_patterns:
        if re.search(pattern, potential_artist, re.IGNORECASE):
            return None, title

    return potential_artist, remaining


def find_similar_artists(
    artist: str, all_artists: List[str], threshold: float = 0.85
) -> List[str]:
    """Find artists with similar names (potential duplicates)."""
    artist_lower = artist.lower()
    similar = []

    for other in all_artists:
        if other.lower() == artist_lower:
            continue
        ratio = SequenceMatcher(None, artist_lower, other.lower()).ratio()
        if ratio >= threshold:
            similar.append((other, ratio))

    return [a for a, _ in sorted(similar, key=lambda x: -x[1])]


# ---------------------------------------------------------------------------
# Tag injection (mutagen-based)
# ---------------------------------------------------------------------------

def _read_existing_replaygain(audio_file: mutagen.FileType) -> Dict[str, str]:
    """Extract existing ReplayGain values to preserve them."""
    preserved: Dict[str, str] = {}

    if isinstance(audio_file, MP3):
        try:
            tags = audio_file.tags or ID3()
            for frame in tags.values():
                if hasattr(frame, "desc") and "replaygain" in (frame.desc or "").lower():
                    preserved[frame.desc] = str(frame)
        except Exception:
            pass

    elif isinstance(audio_file, FLAC):
        for key in list(audio_file.keys()):
            if "replaygain" in key.lower():
                preserved[key] = audio_file[key][0] if audio_file[key] else ""

    elif isinstance(audio_file, MP4):
        for key in list(audio_file.tags.keys()) if audio_file.tags else []:
            if "replaygain" in key.lower():
                val = audio_file.tags[key]
                preserved[key] = val[0].decode("utf-8") if isinstance(val[0], bytes) else str(val[0])

    return preserved


def _restore_replaygain(
    audio_file: mutagen.FileType, preserved: Dict[str, str]
) -> None:
    """Restore preserved ReplayGain values after a tag write."""
    if not preserved:
        return

    if isinstance(audio_file, MP3):
        tags = audio_file.tags
        if tags is None:
            return
        for desc, value in preserved.items():
            tags.add(TXXX(encoding=3, desc=desc, text=[value]))

    elif isinstance(audio_file, FLAC):
        for key, value in preserved.items():
            audio_file[key] = value

    elif isinstance(audio_file, MP4):
        if audio_file.tags is None:
            return
        for key, value in preserved.items():
            audio_file.tags[key] = [value.encode("utf-8")]


def _read_current_tags(filepath: Path) -> Dict[str, Any]:
    """Read current tag values for audit trail."""
    result: Dict[str, Any] = {}
    try:
        audio = mutagen.File(str(filepath), easy=True)
        if audio is None:
            return result
        for key in ["artist", "title", "album", "date", "tracknumber", "discnumber"]:
            val = audio.get(key)
            if val:
                result[key] = val[0] if isinstance(val, list) else str(val)
    except Exception:
        pass
    return result


def inject_tags(
    filepath: Path,
    *,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    track_number: Optional[int] = None,
    disc_number: Optional[int] = None,
    recording_mbid: Optional[str] = None,
    artist_mbid: Optional[str] = None,
    isrc: Optional[str] = None,
    dry_run: bool = True,
) -> TagWriteResult:
    """Write verified metadata into audio file tags.

    Handles:
        - MP3:  ID3v2.3 tags
        - FLAC: Vorbis comments
        - M4A:  MP4 atoms

    Always preserves existing ReplayGain values.
    Writes ``musicbrainz_recordingid`` as a custom tag for future-proofing.

    Args:
        filepath: Path to audio file.
        artist: Verified artist name.
        title: Verified track title.
        album: Verified album name.
        year: Release year (YYYY string).
        track_number: Track number on disc.
        disc_number: Disc number.
        recording_mbid: MusicBrainz Recording ID.
        artist_mbid: MusicBrainz Artist ID.
        isrc: International Standard Recording Code.
        dry_run: If True, report what would change without writing.

    Returns:
        TagWriteResult with before/after snapshots and fields written.
    """
    filepath = Path(filepath)
    result = TagWriteResult(filepath=str(filepath), success=False, action="skip")

    if not filepath.is_file():
        result.action = "error"
        result.error = "file not found"
        return result

    suffix = filepath.suffix.lower()
    if suffix not in {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"}:
        result.action = "skip"
        result.error = f"unsupported format: {suffix}"
        return result

    # Read current state for audit
    result.before = _read_current_tags(filepath)

    if dry_run:
        result.action = "dry_run"
        result.success = True
        # Build what would be written
        planned: List[str] = []
        if artist:
            planned.append("artist")
        if title:
            planned.append("title")
        if album:
            planned.append("album")
        if year:
            planned.append("date")
        if track_number is not None:
            planned.append("tracknumber")
        if disc_number is not None:
            planned.append("discnumber")
        if recording_mbid:
            planned.append("musicbrainz_recordingid")
        if artist_mbid:
            planned.append("musicbrainz_artistid")
        if isrc:
            planned.append("isrc")
        result.fields_written = planned
        return result

    try:
        audio = mutagen.File(str(filepath))
        if audio is None:
            result.action = "error"
            result.error = "mutagen could not open file"
            return result

        # Preserve ReplayGain
        rg_values = _read_existing_replaygain(audio)
        if rg_values:
            result.fields_preserved = list(rg_values.keys())

        fields_written: List[str] = []

        if isinstance(audio, MP3):
            _write_mp3_tags(
                audio, artist=artist, title=title, album=album, year=year,
                track_number=track_number, disc_number=disc_number,
                recording_mbid=recording_mbid, artist_mbid=artist_mbid,
                isrc=isrc, fields_written=fields_written,
            )
        elif isinstance(audio, FLAC):
            _write_flac_tags(
                audio, artist=artist, title=title, album=album, year=year,
                track_number=track_number, disc_number=disc_number,
                recording_mbid=recording_mbid, artist_mbid=artist_mbid,
                isrc=isrc, fields_written=fields_written,
            )
        elif isinstance(audio, MP4):
            _write_mp4_tags(
                audio, artist=artist, title=title, album=album, year=year,
                track_number=track_number, disc_number=disc_number,
                recording_mbid=recording_mbid, artist_mbid=artist_mbid,
                isrc=isrc, fields_written=fields_written,
            )
        else:
            # Fallback: try EasyID3-style interface
            _write_easy_tags(
                audio, artist=artist, title=title, album=album, year=year,
                track_number=track_number, disc_number=disc_number,
                fields_written=fields_written,
            )

        # Restore ReplayGain
        _restore_replaygain(audio, rg_values)

        audio.save()

        result.success = True
        result.action = "write"
        result.fields_written = fields_written
        result.after = _read_current_tags(filepath)

    except Exception as exc:
        result.action = "error"
        result.error = str(exc)
        logger.error("Tag injection failed for %s: %s", filepath.name, exc)

    return result


# ---------------------------------------------------------------------------
# Format-specific tag writers
# ---------------------------------------------------------------------------

def _write_mp3_tags(
    audio: MP3,
    *,
    artist: Optional[str],
    title: Optional[str],
    album: Optional[str],
    year: Optional[str],
    track_number: Optional[int],
    disc_number: Optional[int],
    recording_mbid: Optional[str],
    artist_mbid: Optional[str],
    isrc: Optional[str],
    fields_written: List[str],
) -> None:
    """Write ID3v2.3 tags to an MP3 file."""
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags

    if artist:
        tags["TPE1"] = mutagen.id3.TPE1(encoding=3, text=[artist])
        fields_written.append("artist")

    if title:
        tags["TIT2"] = mutagen.id3.TIT2(encoding=3, text=[title])
        fields_written.append("title")

    if album:
        tags["TALB"] = mutagen.id3.TALB(encoding=3, text=[album])
        fields_written.append("album")

    if year:
        tags["TDRC"] = mutagen.id3.TDRC(encoding=3, text=[year])
        fields_written.append("date")

    if track_number is not None:
        tags["TRCK"] = mutagen.id3.TRCK(encoding=3, text=[str(track_number)])
        fields_written.append("tracknumber")

    if disc_number is not None:
        tags["TPOS"] = mutagen.id3.TPOS(encoding=3, text=[str(disc_number)])
        fields_written.append("discnumber")

    if recording_mbid:
        tags.add(TXXX(encoding=3, desc="musicbrainz_recordingid", text=[recording_mbid]))
        fields_written.append("musicbrainz_recordingid")

    if artist_mbid:
        tags.add(TXXX(encoding=3, desc="musicbrainz_artistid", text=[artist_mbid]))
        fields_written.append("musicbrainz_artistid")

    if isrc:
        tags["TSRC"] = mutagen.id3.TSRC(encoding=3, text=[isrc])
        fields_written.append("isrc")


def _write_flac_tags(
    audio: FLAC,
    *,
    artist: Optional[str],
    title: Optional[str],
    album: Optional[str],
    year: Optional[str],
    track_number: Optional[int],
    disc_number: Optional[int],
    recording_mbid: Optional[str],
    artist_mbid: Optional[str],
    isrc: Optional[str],
    fields_written: List[str],
) -> None:
    """Write Vorbis comments to a FLAC file."""
    if artist:
        audio["artist"] = artist
        fields_written.append("artist")

    if title:
        audio["title"] = title
        fields_written.append("title")

    if album:
        audio["album"] = album
        fields_written.append("album")

    if year:
        audio["date"] = year
        fields_written.append("date")

    if track_number is not None:
        audio["tracknumber"] = str(track_number)
        fields_written.append("tracknumber")

    if disc_number is not None:
        audio["discnumber"] = str(disc_number)
        fields_written.append("discnumber")

    if recording_mbid:
        audio["musicbrainz_recordingid"] = recording_mbid
        fields_written.append("musicbrainz_recordingid")

    if artist_mbid:
        audio["musicbrainz_artistid"] = artist_mbid
        fields_written.append("musicbrainz_artistid")

    if isrc:
        audio["isrc"] = isrc
        fields_written.append("isrc")


def _write_mp4_tags(
    audio: MP4,
    *,
    artist: Optional[str],
    title: Optional[str],
    album: Optional[str],
    year: Optional[str],
    track_number: Optional[int],
    disc_number: Optional[int],
    recording_mbid: Optional[str],
    artist_mbid: Optional[str],
    isrc: Optional[str],
    fields_written: List[str],
) -> None:
    """Write MP4 atoms to an M4A file."""
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags

    if artist:
        tags["\xa9ART"] = [artist]
        fields_written.append("artist")

    if title:
        tags["\xa9nam"] = [title]
        fields_written.append("title")

    if album:
        tags["\xa9alb"] = [album]
        fields_written.append("album")

    if year:
        tags["\xa9day"] = [year]
        fields_written.append("date")

    if track_number is not None:
        # MP4 track number is (track, total) tuple
        existing = tags.get("trkn", [(0, 0)])
        total = existing[0][1] if existing and len(existing[0]) > 1 else 0
        tags["trkn"] = [(track_number, total)]
        fields_written.append("tracknumber")

    if disc_number is not None:
        existing = tags.get("disk", [(0, 0)])
        total = existing[0][1] if existing and len(existing[0]) > 1 else 0
        tags["disk"] = [(disc_number, total)]
        fields_written.append("discnumber")

    if recording_mbid:
        tags["----:com.apple.iTunes:MusicBrainz Track Id"] = [
            recording_mbid.encode("utf-8")
        ]
        fields_written.append("musicbrainz_recordingid")

    if artist_mbid:
        tags["----:com.apple.iTunes:MusicBrainz Artist Id"] = [
            artist_mbid.encode("utf-8")
        ]
        fields_written.append("musicbrainz_artistid")


def _write_easy_tags(
    audio: mutagen.FileType,
    *,
    artist: Optional[str],
    title: Optional[str],
    album: Optional[str],
    year: Optional[str],
    track_number: Optional[int],
    disc_number: Optional[int],
    fields_written: List[str],
) -> None:
    """Fallback writer using mutagen's easy interface (OGG, Opus, etc.)."""
    if artist:
        audio["artist"] = [artist]
        fields_written.append("artist")
    if title:
        audio["title"] = [title]
        fields_written.append("title")
    if album:
        audio["album"] = [album]
        fields_written.append("album")
    if year:
        audio["date"] = [year]
        fields_written.append("date")
    if track_number is not None:
        audio["tracknumber"] = [str(track_number)]
        fields_written.append("tracknumber")
    if disc_number is not None:
        audio["discnumber"] = [str(disc_number)]
        fields_written.append("discnumber")


# ---------------------------------------------------------------------------
# Library-wide normalization (database level)
# ---------------------------------------------------------------------------

def normalize_library(
    db_path: str = "lyra_registry.db",
    apply: bool = False,
    output_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Normalize all metadata in the library database.

    Operates in plan mode by default. Generates a JSON audit log of all
    proposed changes. Use ``apply=True`` to execute.

    Args:
        db_path: Path to SQLite database.
        apply: If True, write changes to the database.
        output_path: Optional path for JSON audit log.

    Returns:
        List of change dicts.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT track_id, artist, title, filepath FROM tracks
        WHERE status = 'active'
        ORDER BY artist, title
    """)
    tracks = cursor.fetchall()

    logger.info("Analyzing %d tracks for normalization...", len(tracks))

    changes: List[Dict[str, Any]] = []
    artist_counts: Dict[str, int] = defaultdict(int)

    for track_id, artist, title, filepath in tracks:
        norm_artist, feat_from_artist = normalize_artist(artist or "")
        norm_title, feat_from_title = normalize_title(title or "")
        all_featured = feat_from_artist + feat_from_title

        # Try extracting artist from title if missing
        if not norm_artist or norm_artist.lower() in {"", "unknown", "various", "various artists"}:
            extracted, norm_title = extract_artist_from_title(norm_title)
            if extracted:
                norm_artist, _ = normalize_artist(extracted)

        artist_counts[norm_artist] += 1

        if norm_artist != (artist or "") or norm_title != (title or ""):
            changes.append({
                "track_id": track_id,
                "old_artist": artist,
                "new_artist": norm_artist,
                "old_title": title,
                "new_title": norm_title,
                "featured": all_featured,
                "filepath": filepath,
            })

    # Find similar artist names
    all_artists = list(artist_counts.keys())
    similar_groups: Dict[str, set] = defaultdict(set)
    for a in all_artists:
        similar = find_similar_artists(a, all_artists)
        if similar:
            key = min([a] + similar, key=str.lower)
            similar_groups[key].add(a)
            for s in similar:
                similar_groups[key].add(s)

    # Report
    logger.info("Normalization analysis: %d changes, %d similar-artist groups",
                len(changes), len(similar_groups))

    # Write audit log
    if output_path or not apply:
        audit = {
            "timestamp": time.time(),
            "total_tracks": len(tracks),
            "changes_proposed": len(changes),
            "similar_artist_groups": {
                k: list(v) for k, v in similar_groups.items() if len(v) > 1
            },
            "changes": changes,
        }
        log_path = Path(output_path) if output_path else Path(f"normalize_plan_{int(time.time())}.json")
        log_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Audit log written to %s", log_path)

    if not apply:
        logger.info("Dry run: %d changes proposed. Use --apply to execute.", len(changes))
        conn.close()
        return changes

    # Apply all changes in a single batch transaction.
    cursor.executemany(
        "UPDATE tracks SET artist = ?, title = ? WHERE track_id = ?",
        [(c["new_artist"], c["new_title"], c["track_id"]) for c in changes],
    )
    applied = len(changes)

    conn.commit()
    conn.close()
    logger.info("Applied %d normalization changes", applied)

    return changes


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Normalize library metadata")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--db", default="lyra_registry.db", help="Database path")
    parser.add_argument("--output", help="Output path for audit JSON")

    args = parser.parse_args()
    normalize_library(args.db, apply=args.apply, output_path=args.output)
