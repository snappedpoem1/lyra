#!/usr/bin/env python3
"""xray_tags.py - Raw binary tag diagnostic tool.

Reads and displays all metadata tags from audio files using mutagen's
low-level interfaces (not EasyID3). Useful for verifying the tag injection
pipeline wrote correct values.

Features:
    - Displays raw ID3v2 frames (MP3), Vorbis comments (FLAC), MP4 atoms (M4A)
    - Highlights MusicBrainz IDs (recording, artist, release)
    - Checks ReplayGain preservation
    - Validates tag encoding (UTF-8, Latin-1)
    - Supports single file, directory scan, or database track ID lookup
    - JSON output mode for programmatic consumption

Usage:
    # Single file
    python scripts/xray_tags.py "/path/to/library/Artist/Album/01 - Track.flac"

    # Directory scan (all audio files)
    python scripts/xray_tags.py "/path/to/library/Artist/Album/" --recursive

    # By track ID from database
    python scripts/xray_tags.py --track-id abc123def456

    # JSON output
    python scripts/xray_tags.py file.flac --json

    # Show only MusicBrainz + ReplayGain tags
    python scripts/xray_tags.py file.flac --filter mb,rg

    # Verify pipeline success (check for required tags)
    python scripts/xray_tags.py "/path/to/library" --verify --recursive
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

logger = logging.getLogger("xray_tags")

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".aiff", ".wma"}

# Tags we consider "required" for a properly processed file
REQUIRED_TAGS = {"artist", "title", "album"}
MUSICBRAINZ_TAGS = {"musicbrainz_recordingid", "musicbrainz_artistid", "musicbrainz_releaseid"}
REPLAYGAIN_TAGS = {
    "replaygain_track_gain", "replaygain_track_peak",
    "replaygain_album_gain", "replaygain_album_peak",
}


# ---------------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------------

def xray_file(filepath: Path) -> Dict[str, Any]:
    """Extract all raw tags from an audio file.

    Returns a structured dict with format info and all tag key-value pairs.
    """
    filepath = Path(filepath)
    result: Dict[str, Any] = {
        "filepath": str(filepath),
        "filename": filepath.name,
        "extension": filepath.suffix.lower(),
        "size_bytes": filepath.stat().st_size if filepath.is_file() else 0,
        "format": None,
        "duration_seconds": None,
        "bitrate": None,
        "sample_rate": None,
        "channels": None,
        "tags": {},
        "musicbrainz": {},
        "replaygain": {},
        "warnings": [],
        "errors": [],
    }

    if not filepath.is_file():
        result["errors"].append("file not found")
        return result

    try:
        audio = mutagen.File(str(filepath))
    except Exception as exc:
        result["errors"].append(f"mutagen open failed: {exc}")
        return result

    if audio is None:
        result["errors"].append("mutagen returned None (unsupported format?)")
        return result

    # Audio info
    if hasattr(audio, "info") and audio.info:
        info = audio.info
        result["duration_seconds"] = round(getattr(info, "length", 0), 2)
        result["bitrate"] = getattr(info, "bitrate", None)
        result["sample_rate"] = getattr(info, "sample_rate", None)
        result["channels"] = getattr(info, "channels", None)

        # Bits per sample for FLAC
        if hasattr(info, "bits_per_sample"):
            result["bits_per_sample"] = info.bits_per_sample

    # Format detection and raw tag extraction
    if isinstance(audio, MP3):
        result["format"] = "MP3/ID3"
        _extract_id3(audio, result)
    elif isinstance(audio, FLAC):
        result["format"] = "FLAC/Vorbis"
        _extract_vorbis(audio, result)
    elif isinstance(audio, MP4):
        result["format"] = "MP4/iTunes"
        _extract_mp4(audio, result)
    else:
        result["format"] = type(audio).__name__
        _extract_generic(audio, result)

    return result


def _extract_id3(audio: MP3, result: Dict[str, Any]) -> None:
    """Extract all ID3v2 frames from an MP3."""
    tags = audio.tags
    if tags is None:
        result["warnings"].append("no ID3 tags found")
        return

    result["id3_version"] = f"ID3v2.{tags.version[1]}" if hasattr(tags, "version") else "unknown"

    for key, frame in tags.items():
        frame_id = key.split(":")[0] if ":" in key else key
        value = _frame_to_string(frame)

        # Categorize
        key_lower = key.lower()
        desc_lower = getattr(frame, "desc", "").lower() if hasattr(frame, "desc") else ""

        if "musicbrainz" in desc_lower or "musicbrainz" in key_lower:
            mb_key = desc_lower or key_lower
            result["musicbrainz"][mb_key] = value
        elif "replaygain" in desc_lower or "replaygain" in key_lower:
            rg_key = desc_lower or key_lower
            result["replaygain"][rg_key] = value
        else:
            result["tags"][key] = {
                "value": value,
                "frame_type": type(frame).__name__,
                "encoding": _get_encoding(frame),
            }


def _extract_vorbis(audio: FLAC, result: Dict[str, Any]) -> None:
    """Extract all Vorbis comments from a FLAC."""
    if not audio.tags:
        result["warnings"].append("no Vorbis comments found")
        return

    # VorbisComment keys are accessed via .keys() method
    for key in list(audio.tags.keys()):
        values = audio.tags[key]
        value = values[0] if isinstance(values, list) and len(values) == 1 else values
        key_lower = key.lower()

        if "musicbrainz" in key_lower:
            result["musicbrainz"][key_lower] = value
        elif "replaygain" in key_lower:
            result["replaygain"][key_lower] = value
        else:
            result["tags"][key] = {"value": value}

    # Picture info
    if audio.pictures:
        pics = []
        for pic in audio.pictures:
            pics.append({
                "type": pic.type,
                "mime": pic.mime,
                "width": pic.width,
                "height": pic.height,
                "size_bytes": len(pic.data),
            })
        result["pictures"] = pics


def _extract_mp4(audio: MP4, result: Dict[str, Any]) -> None:
    """Extract all MP4 atoms from an M4A/MP4."""
    if audio.tags is None:
        result["warnings"].append("no MP4 tags found")
        return

    # MP4 atom name mapping
    atom_names = {
        "\xa9nam": "title",
        "\xa9ART": "artist",
        "\xa9alb": "album",
        "\xa9day": "date",
        "\xa9gen": "genre",
        "\xa9wrt": "composer",
        "\xa9cmt": "comment",
        "aART": "album_artist",
        "trkn": "track_number",
        "disk": "disc_number",
        "covr": "cover_art",
        "tmpo": "bpm",
        "cpil": "compilation",
    }

    for key, value in audio.tags.items():
        friendly_name = atom_names.get(key, key)
        key_lower = key.lower()

        if "musicbrainz" in key_lower or "musicbrainz" in friendly_name.lower():
            # Decode bytes if needed
            if isinstance(value, list) and value and isinstance(value[0], bytes):
                result["musicbrainz"][friendly_name] = value[0].decode("utf-8", errors="replace")
            else:
                result["musicbrainz"][friendly_name] = _mp4_value_to_string(value)
        elif "replaygain" in key_lower or "replaygain" in friendly_name.lower():
            if isinstance(value, list) and value and isinstance(value[0], bytes):
                result["replaygain"][friendly_name] = value[0].decode("utf-8", errors="replace")
            else:
                result["replaygain"][friendly_name] = _mp4_value_to_string(value)
        elif key == "covr":
            pics = []
            for pic in value:
                pics.append({
                    "format": "JPEG" if getattr(pic, "imageformat", 0) == 13 else "PNG",
                    "size_bytes": len(bytes(pic)),
                })
            result["pictures"] = pics
        else:
            result["tags"][friendly_name] = {"value": _mp4_value_to_string(value)}


def _extract_generic(audio: mutagen.FileType, result: Dict[str, Any]) -> None:
    """Fallback extraction for other formats."""
    if audio.tags is None:
        result["warnings"].append("no tags found")
        return

    for key in audio.tags:
        value = audio.tags[key]
        key_lower = key.lower()

        if "musicbrainz" in key_lower:
            result["musicbrainz"][key_lower] = str(value)
        elif "replaygain" in key_lower:
            result["replaygain"][key_lower] = str(value)
        else:
            val = value[0] if isinstance(value, list) and len(value) == 1 else str(value)
            result["tags"][key] = {"value": val}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frame_to_string(frame: Any) -> str:
    """Convert an ID3 frame to a readable string."""
    if hasattr(frame, "text"):
        return "; ".join(str(t) for t in frame.text)
    if hasattr(frame, "url"):
        return frame.url
    if hasattr(frame, "data"):
        return f"<binary {len(frame.data)} bytes>"
    return str(frame)


def _get_encoding(frame: Any) -> Optional[str]:
    """Get the text encoding of an ID3 frame."""
    if not hasattr(frame, "encoding"):
        return None
    encoding_map = {0: "Latin-1", 1: "UTF-16", 2: "UTF-16BE", 3: "UTF-8"}
    return encoding_map.get(frame.encoding, f"unknown({frame.encoding})")


def _mp4_value_to_string(value: Any) -> str:
    """Convert MP4 atom value to string."""
    if isinstance(value, list):
        parts = []
        for v in value:
            if isinstance(v, bytes):
                parts.append(v.decode("utf-8", errors="replace"))
            elif isinstance(v, tuple):
                parts.append(f"{v[0]}/{v[1]}" if len(v) == 2 else str(v))
            else:
                parts.append(str(v))
        return "; ".join(parts)
    return str(value)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_file(filepath: Path) -> Dict[str, Any]:
    """Check if a file has all required tags after pipeline processing."""
    data = xray_file(filepath)
    issues: List[str] = []

    if data["errors"]:
        return {"filepath": str(filepath), "status": "error", "issues": data["errors"]}

    # Check required tags
    tag_keys = {k.lower() for k in data["tags"]}
    # Also check actual values
    tag_values = {}
    for k, v in data["tags"].items():
        val = v.get("value", "") if isinstance(v, dict) else str(v)
        tag_values[k.lower()] = val

    # ID3 frame mapping to generic names
    id3_map = {
        "tpe1": "artist", "tit2": "title", "talb": "album",
        "tdrc": "date", "trck": "tracknumber",
    }
    normalized_tags = set()
    for k in tag_keys:
        normalized_tags.add(id3_map.get(k, k))

    for req in REQUIRED_TAGS:
        if req not in normalized_tags:
            issues.append(f"missing required tag: {req}")

    # Check MusicBrainz IDs
    has_mb = bool(data["musicbrainz"])
    if not has_mb:
        issues.append("no MusicBrainz IDs found")

    if "musicbrainz_recordingid" not in {k.lower() for k in data["musicbrainz"]}:
        mb_keys_lower = {k.lower().replace(" ", "_") for k in data["musicbrainz"]}
        if "musicbrainz_recordingid" not in mb_keys_lower and "musicbrainz_track_id" not in mb_keys_lower:
            issues.append("missing musicbrainz_recordingid")

    # Check encoding
    for k, v in data["tags"].items():
        if isinstance(v, dict) and v.get("encoding") == "Latin-1":
            issues.append(f"tag '{k}' uses Latin-1 encoding (should be UTF-8)")

    status = "ok" if not issues else "issues"
    return {
        "filepath": str(filepath),
        "status": status,
        "issues": issues,
        "has_musicbrainz": has_mb,
        "has_replaygain": bool(data["replaygain"]),
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_xray(data: Dict[str, Any], filters: Optional[List[str]] = None) -> None:
    """Pretty-print xray results to terminal."""
    print(f"\n{'=' * 70}")
    print(f"FILE: {data['filename']}")
    print(f"{'=' * 70}")
    print(f"  Path:       {data['filepath']}")
    print(f"  Format:     {data['format']}")
    print(f"  Size:       {data['size_bytes']:,} bytes ({data['size_bytes'] / 1024 / 1024:.1f} MB)")
    if data.get("duration_seconds"):
        mins = int(data["duration_seconds"] // 60)
        secs = data["duration_seconds"] % 60
        print(f"  Duration:   {mins}:{secs:05.2f}")
    if data.get("bitrate"):
        print(f"  Bitrate:    {data['bitrate']:,} bps")
    if data.get("sample_rate"):
        print(f"  Sample:     {data['sample_rate']:,} Hz")
    if data.get("bits_per_sample"):
        print(f"  Bit depth:  {data['bits_per_sample']}-bit")
    if data.get("channels"):
        print(f"  Channels:   {data['channels']}")
    if data.get("id3_version"):
        print(f"  ID3:        {data['id3_version']}")

    show_all = not filters
    show_tags = show_all or "tags" in filters
    show_mb = show_all or "mb" in filters
    show_rg = show_all or "rg" in filters

    if show_tags and data["tags"]:
        print(f"\n  --- Tags ({len(data['tags'])}) ---")
        for key, info in sorted(data["tags"].items()):
            value = info.get("value", info) if isinstance(info, dict) else info
            enc = info.get("encoding") if isinstance(info, dict) else None
            enc_str = f" [{enc}]" if enc else ""
            # Truncate long values
            val_str = str(value)[:100]
            if len(str(value)) > 100:
                val_str += "..."
            print(f"    {key:30s} = {val_str}{enc_str}")

    if show_mb:
        if data["musicbrainz"]:
            print(f"\n  --- MusicBrainz IDs ---")
            for key, value in sorted(data["musicbrainz"].items()):
                print(f"    {key:35s} = {value}")
        else:
            print(f"\n  --- MusicBrainz IDs: NONE ---")

    if show_rg:
        if data["replaygain"]:
            print(f"\n  --- ReplayGain ---")
            for key, value in sorted(data["replaygain"].items()):
                print(f"    {key:35s} = {value}")
        else:
            print(f"\n  --- ReplayGain: NONE ---")

    if data.get("pictures"):
        print(f"\n  --- Embedded Pictures ---")
        for pic in data["pictures"]:
            fmt = pic.get("format") or pic.get("mime", "?")
            size = pic.get("size_bytes", 0)
            dims = ""
            if pic.get("width") and pic.get("height"):
                dims = f" ({pic['width']}x{pic['height']})"
            print(f"    {fmt}{dims} Ã¢â‚¬â€ {size:,} bytes")

    if data["warnings"]:
        print(f"\n  --- Warnings ---")
        for w in data["warnings"]:
            print(f"    ! {w}")

    if data["errors"]:
        print(f"\n  --- Errors ---")
        for e in data["errors"]:
            print(f"    X {e}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _safe_print(text: str) -> None:
    """Print with fallback for Windows cp1252 encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def main() -> None:
    # Force UTF-8 stdout on Windows to avoid cp1252 errors
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="X-ray audio file tags Ã¢â‚¬â€ raw binary tag reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="File or directory to scan",
    )
    parser.add_argument(
        "--track-id",
        help="Look up filepath by track_id in lyra_registry.db",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recursively scan directories",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--filter",
        help="Comma-separated tag categories to show: tags,mb,rg (default: all)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify pipeline success (check required tags)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max files to process (0 = all)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    filters = args.filter.split(",") if args.filter else None

    # Resolve target files
    files: List[Path] = []

    if args.track_id:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        from oracle.db.schema import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filepath FROM tracks WHERE track_id = ?", (args.track_id,))
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            print(f"Track {args.track_id} not found or has no filepath")
            sys.exit(1)
        files.append(Path(row[0]))

    elif args.path:
        target = Path(args.path)
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            pattern = "**/*" if args.recursive else "*"
            for p in sorted(target.glob(pattern)):
                if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                    files.append(p)
        else:
            print(f"Path not found: {args.path}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(0)

    if args.limit > 0:
        files = files[:args.limit]

    if not files:
        print("No audio files found.")
        sys.exit(0)

    # Process files
    all_results: List[Dict[str, Any]] = []
    verify_results: List[Dict[str, Any]] = []

    for filepath in files:
        data = xray_file(filepath)
        all_results.append(data)

        if args.verify:
            vr = verify_file(filepath)
            verify_results.append(vr)

        if not args.json_output and not args.verify:
            print_xray(data, filters=filters)

    # Output
    if args.json_output:
        output = all_results if not args.verify else verify_results
        print(json.dumps(output, indent=2, ensure_ascii=False))

    elif args.verify:
        # Verification summary
        ok = sum(1 for v in verify_results if v["status"] == "ok")
        issues = sum(1 for v in verify_results if v["status"] == "issues")
        errors = sum(1 for v in verify_results if v["status"] == "error")
        total = len(verify_results)

        print(f"\n{'=' * 60}")
        print(f"VERIFICATION SUMMARY: {total} files")
        print(f"{'=' * 60}")
        print(f"  OK:     {ok}")
        print(f"  Issues: {issues}")
        print(f"  Errors: {errors}")

        if issues > 0 or errors > 0:
            print(f"\n  --- Files with issues ---")
            for v in verify_results:
                if v["status"] != "ok":
                    print(f"  [{v['status'].upper()}] {Path(v['filepath']).name}")
                    for issue in v.get("issues", []):
                        print(f"         {issue}")
            print()

        # MB coverage stats
        mb_count = sum(1 for v in verify_results if v.get("has_musicbrainz"))
        rg_count = sum(1 for v in verify_results if v.get("has_replaygain"))
        print(f"  MusicBrainz IDs: {mb_count}/{total} ({mb_count/total*100:.0f}%)" if total else "")
        print(f"  ReplayGain:      {rg_count}/{total} ({rg_count/total*100:.0f}%)" if total else "")
        print()


if __name__ == "__main__":
    main()
