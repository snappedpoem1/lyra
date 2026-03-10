"""Audit a Spotify-style playlist export against the local Lyra library.

Usage:
  python scripts/analyze_playlist_export.py
  python scripts/analyze_playlist_export.py --playlist-json "C:/path/Playlist1.json" --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

DEFAULT_EXPORT = Path("C:/Users/Admin/Documents/LYRA PROJECT/Playlist1.json")
DEFAULT_DB = Path("C:/MusicOracle/lyra_registry.db")


def _norm(value: str) -> str:
    text = (value or "").strip().lower()
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            cleaned.append(ch)
    return " ".join("".join(cleaned).split())


def _load_export(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_export_tracks(payload: Dict[str, Any]) -> Iterable[Tuple[str, str, str]]:
    for playlist in payload.get("playlists", []):
        playlist_name = str(playlist.get("name") or "Unnamed Playlist").strip()
        for item in playlist.get("items", []):
            track = item.get("track") or {}
            artist = str(track.get("artistName") or "").strip()
            title = str(track.get("trackName") or "").strip()
            if artist and title:
                yield playlist_name, artist, title


def _load_library_index(db_path: Path) -> Dict[Tuple[str, str], List[Dict[str, str]]]:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT track_id, artist, title, COALESCE(album, '')
        FROM tracks
        WHERE status = 'active'
        """
    )
    index: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for track_id, artist, title, album in cursor.fetchall():
        key = (_norm(str(artist)), _norm(str(title)))
        index.setdefault(key, []).append(
            {
                "track_id": str(track_id),
                "artist": str(artist),
                "title": str(title),
                "album": str(album),
            }
        )
    conn.close()
    return index


def audit_playlist_export(export_path: Path, db_path: Path) -> Dict[str, Any]:
    payload = _load_export(export_path)
    library_index = _load_library_index(db_path)

    playlists_seen = Counter()
    artists_seen = Counter()
    total = 0
    matched = 0
    unmatched: List[Dict[str, str]] = []

    for playlist_name, artist, title in _iter_export_tracks(payload):
        total += 1
        playlists_seen[playlist_name] += 1
        artists_seen[artist] += 1
        key = (_norm(artist), _norm(title))
        if key in library_index:
            matched += 1
            continue
        unmatched.append({"playlist": playlist_name, "artist": artist, "title": title})

    top_artists = [name for name, _count in artists_seen.most_common(8)]
    prompt = ""
    if top_artists:
        prompt = (
            "Build a playlist from my local library with the vibe and energy of "
            + ", ".join(top_artists[:4])
            + ", with modern bass, cinematic transitions, and clean sequencing."
        )

    return {
        "export_path": str(export_path),
        "db_path": str(db_path),
        "total_tracks": total,
        "matched_tracks": matched,
        "missing_tracks": total - matched,
        "match_rate": round((matched / total) if total else 0.0, 4),
        "playlist_counts": dict(playlists_seen),
        "top_reference_artists": top_artists,
        "suggested_vibe_prompt": prompt,
        "missing_examples": unmatched[:25],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit playlist export coverage against local library.")
    parser.add_argument("--playlist-json", default=str(DEFAULT_EXPORT), help="Path to playlist export JSON")
    parser.add_argument("--db-path", default=str(DEFAULT_DB), help="Path to lyra_registry.db")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    export_path = Path(args.playlist_json)
    db_path = Path(args.db_path)

    if not export_path.exists():
        print(f"Export file not found: {export_path}")
        return 2
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return 3

    report = audit_playlist_export(export_path, db_path)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("Playlist Export Audit")
    print(f"Export: {report['export_path']}")
    print(f"Library DB: {report['db_path']}")
    print(f"Tracks matched: {report['matched_tracks']} / {report['total_tracks']} ({report['match_rate'] * 100:.1f}%)")
    print(f"Missing tracks: {report['missing_tracks']}")
    if report["top_reference_artists"]:
        print("Top reference artists: " + ", ".join(report["top_reference_artists"][:8]))
    if report["suggested_vibe_prompt"]:
        print("Suggested vibe prompt:")
        print(report["suggested_vibe_prompt"])
    if report["missing_examples"]:
        print("Missing examples:")
        for item in report["missing_examples"][:10]:
            print(f"  - {item['artist']} - {item['title']} [{item['playlist']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
