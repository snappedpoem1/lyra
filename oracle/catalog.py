"""Catalog-first acquisition — verified discography from MusicBrainz.

Looks up an artist's real discography via MusicBrainz, filters to actual
studio albums/EPs, then acquires full albums via Prowlarr + Real-Debrid.

Usage:
    oracle catalog lookup "Brand New"
    oracle catalog acquire "Brand New" --dry-run
    oracle catalog acquire "Brand New" --limit 1
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection
from oracle.enrichers.musicbrainz import (
    get_release_groups,
    get_releases_for_group,
    search_artist,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MusicBrainz discography lookup
# ---------------------------------------------------------------------------

# Secondary types that indicate non-standard releases
_SKIP_SECONDARY_TYPES = {"compilation", "dj-mix", "mixtape/street", "remix", "soundtrack"}

# Patterns in release-group titles that indicate live recordings
_LIVE_TITLE_RE = re.compile(
    r"\bLive\s+(at|from|in)\b|\d{4}-\d{2}-\d{2}[\s:]", re.IGNORECASE
)
<<<<<<< HEAD
=======
_LOW_PRIORITY_TITLE_RE = re.compile(
    r"\b(demo|untitled|instrumental|era|lullaby)\b", re.IGNORECASE
)
>>>>>>> fc77b41 (Update workspace state and diagnostics)


def lookup_artist(name: str) -> Optional[Dict[str, Any]]:
    """Search MusicBrainz for an artist, return best match.

    Returns:
        Dict with 'id', 'name', 'type', 'disambiguation', 'score'
        or None if not found.
    """
    data = search_artist(name, limit=5)
    artists = data.get("artists", [])
    if not artists:
        return None

    # Prefer exact-name match with type=Group (bands) or Person
    for a in artists:
        if a.get("score", 0) >= 95 and a.get("name", "").lower() == name.lower():
            return a

    # Fall back to highest-scoring result
    best = artists[0]
    if best.get("score", 0) >= 80:
        return best

    return None


def get_discography(
    artist_mbid: str,
    types: Optional[List[str]] = None,
    include_live: bool = False,
) -> List[Dict[str, Any]]:
    """Get an artist's release groups from MusicBrainz.

    Args:
        artist_mbid: MusicBrainz artist ID.
        types: Release types to include (default: album, ep).
        include_live: Whether to include live albums.

    Returns:
        List of release group dicts sorted by year.
    """
    if types is None:
        types = ["album", "ep"]

    all_groups: List[Dict[str, Any]] = []
    for rtype in types:
        offset = 0
        while True:
            data = get_release_groups(artist_mbid, rtype, offset=offset)
            groups = data.get("release-groups", [])
            if not groups:
                break
            all_groups.extend(groups)
            offset += len(groups)
            if offset >= data.get("release-group-count", 0):
                break

    # Filter out compilations, soundtracks, live albums
    filtered: List[Dict[str, Any]] = []
    for rg in all_groups:
        secondary = {s.lower() for s in rg.get("secondary-types", [])}
        if secondary & _SKIP_SECONDARY_TYPES:
            continue

        title = rg.get("title", "")

        # Skip live albums unless explicitly requested
        if not include_live and _LIVE_TITLE_RE.search(title):
            continue

        year_str = (rg.get("first-release-date") or "")[:4]
        year = int(year_str) if year_str.isdigit() else None

        filtered.append({
            "rgid": rg["id"],
            "title": title,
            "type": rg.get("primary-type", "Album"),
            "year": year,
        })

    # Sort by year (None last)
    filtered.sort(key=lambda r: (r["year"] or 9999, r["title"]))
    return filtered


def get_album_tracks(release_group_mbid: str) -> Dict[str, Any]:
    """Get the canonical track listing for a release group.

    Picks the best release (US/XW, official, non-deluxe) and extracts
    the track listing with artist credits.

    Returns:
        Dict with 'release_mbid', 'title', 'date', 'country',
        'tracks': [{position, title, duration_ms, is_primary}]
    """
    data = get_releases_for_group(release_group_mbid)
    releases = data.get("releases", [])
    if not releases:
        return {}

    # Score releases to pick the best one
    def _score_release(rel: Dict) -> Tuple[int, int, int]:
        score = 0
        country = (rel.get("country") or "").upper()
        status = (rel.get("status") or "").lower()

        media = rel.get("media", [])
        track_count = sum(m.get("track-count", 0) for m in media)

        # Prefer official releases
        if status == "official":
            score += 10
        # Prefer US/worldwide/GB
        if country in ("US", "XW", "GB"):
            score += 5
        # Penalize releases with very few tracks (vinyl singles, etc.)
        if track_count <= 1:
            score -= 20

        # Prefer more tracks (deluxe with bonus tracks is fine)
        return (score, track_count, 0)

    releases.sort(key=_score_release, reverse=True)
    best = releases[0]

    tracks: List[Dict[str, Any]] = []
    for medium in best.get("media", []):
        for t in medium.get("tracks", []):
            rec = t.get("recording", {})
            duration = rec.get("length")

            tracks.append({
                "position": t.get("position", 0),
                "title": t.get("title", rec.get("title", "")),
                "duration_ms": duration,
            })

    return {
        "release_mbid": best.get("id"),
        "title": best.get("title", ""),
        "date": best.get("date", ""),
        "country": best.get("country", ""),
        "tracks": tracks,
    }


# ---------------------------------------------------------------------------
# Library deduplication
# ---------------------------------------------------------------------------

def check_album_in_library(artist: str, album_title: str) -> Dict[str, Any]:
    """Check how much of an album already exists in the tracks table.

    Returns:
        Dict with 'owned_count', 'total_expected' (0 if unknown),
        'percentage', 'owned_titles'.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT title, album FROM tracks WHERE status = 'active'"
    ).fetchall()
    conn.close()

<<<<<<< HEAD
    artist_lower = artist.lower()
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    album_lower = album_title.lower()
    owned: List[str] = []

    for title, album in rows:
        album_str = (album or "").lower()
        if SequenceMatcher(None, album_lower, album_str).ratio() > 0.75:
            owned.append(title or "")

    return {
        "owned_count": len(owned),
        "owned_titles": owned,
    }


# ---------------------------------------------------------------------------
# Album-level acquisition via Prowlarr + Real-Debrid
# ---------------------------------------------------------------------------

_AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma"}
_LOSSLESS_EXTENSIONS = {".flac", ".wav", ".aiff", ".alac"}


def _sanitize_name(value: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", (value or "").strip())
    s = re.sub(r"\s+", " ", s).strip(". ")
    return s or "Unknown"


def _normalize_title(value: str) -> str:
    s = (value or "").lower()
    s = s.replace("…", "...")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _quality_rank(path: Path) -> float:
    ext = path.suffix.lower()
    if ext in _LOSSLESS_EXTENSIONS:
        return 5.0
    if ext in {".m4a", ".aac", ".opus", ".ogg"}:
        return 3.0
    if ext in {".mp3", ".wma"}:
        try:
            import mutagen
            audio = mutagen.File(str(path))
            bitrate = int(getattr(getattr(audio, "info", None), "bitrate", 0) or 0)
            if bitrate >= 320000:
                return 2.8
            if bitrate >= 256000:
                return 2.6
        except Exception:
            pass
        return 2.0
    return 1.0


def _is_high_quality_album(files: List[Path]) -> bool:
    if not files:
        return False
    lossless = sum(1 for f in files if f.suffix.lower() in _LOSSLESS_EXTENSIONS)
    ratio = lossless / max(len(files), 1)
    return ratio >= 0.8


def _existing_track_candidates(artist: str, title: str) -> List[Path]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT artist, title, filepath FROM tracks WHERE status = 'active' AND filepath IS NOT NULL"
    ).fetchall()
    conn.close()

    artist_norm = _normalize_title(artist)
    title_norm = _normalize_title(title)
    out: List[Path] = []
    for db_artist, db_title, db_path in rows:
        if not db_path:
            continue
        db_artist_norm = _normalize_title(db_artist or "")
        db_title_norm = _normalize_title(db_title or "")
        if SequenceMatcher(None, artist_norm, db_artist_norm).ratio() < 0.85:
            continue
        if SequenceMatcher(None, title_norm, db_title_norm).ratio() < 0.75:
            continue
        out.append(Path(db_path))
    return out


def _promote_album_and_replace_existing(
    artist: str,
    album_title: str,
    year: Optional[int],
    matched: List[Dict[str, Any]],
) -> Dict[str, Any]:
    library_root = Path(LIBRARY_BASE)
    album_folder = _sanitize_name(album_title)
    if year:
        album_folder = f"{album_folder} ({year})"
    artist_folder = _sanitize_name(artist)
    target_dir = library_root / artist_folder / album_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    replaced_root = library_root.parent / "_Replaced_By_Album" / _sanitize_name(f"{artist} - {album_title}")
    replaced_root.mkdir(parents=True, exist_ok=True)

    promoted = 0
    replaced = 0
    archived_conflicts = 0
    skipped = 0

    for item in sorted(matched, key=lambda x: x.get("position", 999)):
        src = Path(item["file_path"])
        if not src.exists():
            skipped += 1
            continue

        title = item.get("track_title", src.stem)
        pos = int(item.get("position", 0) or 0)
        new_name = f"{pos:02d} - {_sanitize_name(title)}{src.suffix}" if pos > 0 else f"{_sanitize_name(title)}{src.suffix}"
        dest = target_dir / new_name

        # Replace existing canonical destination if present.
        if dest.exists():
            archive_dest = replaced_root / f"{int(time.time())}_{dest.name}"
            shutil.move(str(dest), str(archive_dest))
            archived_conflicts += 1

        # Replace lower/equal-quality matches elsewhere in library.
        new_rank = _quality_rank(src)
        for existing in _existing_track_candidates(artist, title):
            if not existing.exists():
                continue
            try:
                if existing.resolve() == src.resolve():
                    continue
            except Exception:
                pass
            old_rank = _quality_rank(existing)
            if new_rank > old_rank:
                archive_dest = replaced_root / f"{int(time.time())}_{existing.name}"
                try:
                    shutil.move(str(existing), str(archive_dest))
                    replaced += 1
                except Exception:
                    pass

        shutil.move(str(src), str(dest))
        promoted += 1
        item["file_path"] = str(dest)

    return {
        "promoted": promoted,
        "replaced_existing": replaced,
        "archived_conflicts": archived_conflicts,
        "skipped": skipped,
        "target_dir": str(target_dir),
        "archive_dir": str(replaced_root),
    }


def acquire_album(
    artist: str,
    album_title: str,
    expected_tracks: List[Dict[str, Any]],
    max_torrent_gb: float = 5.0,
    download_wait: int = 120,
    file_select_wait: int = 15,
    poll_interval: int = 3,
) -> Dict[str, Any]:
    """Acquire a full album via Prowlarr search + Real-Debrid download.

    Searches for the full album torrent, downloads ALL audio files.

    Returns:
        Dict with 'success', 'files', 'matched', 'missing', 'error'.
    """
    from oracle.acquirers.prowlarr_rd import search_prowlarr
    from oracle.acquirers.realdebrid import (
        add_magnet,
        delete_torrent,
        download_torrent_files,
        get_torrent_info,
        select_files,
    )

    max_bytes = int(max_torrent_gb * 1024 ** 3)

    # Build download directory for this album
    project_root = Path(__file__).resolve().parents[1]
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", f"{artist} - {album_title}")
    album_dir = (project_root / "downloads" / safe_name).resolve()
    album_dir.mkdir(parents=True, exist_ok=True)

    # Search Prowlarr for the full album
    queries = [
        f"{artist} {album_title} FLAC",
        f"{artist} {album_title}",
    ]

    results: List[Dict] = []
    for query in queries:
        try:
            hits = search_prowlarr(query, limit=10)
            results.extend(hits)
        except Exception as exc:
            logger.warning(f"[catalog] Prowlarr search failed for '{query}': {exc}")

    if not results:
<<<<<<< HEAD
=======
        fallback = _acquire_album_via_qobuz(artist, album_title, expected_tracks, album_dir)
        if fallback.get("success"):
            return fallback
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        return {"success": False, "error": "No Prowlarr results", "files": []}

    # Deduplicate by infoHash
    seen_hashes: set = set()
    unique: List[Dict] = []
    for r in results:
        h = (r.get("infoHash") or "").lower()
        if h and h in seen_hashes:
            continue
        if h:
            seen_hashes.add(h)
        unique.append(r)

    # Sort: prefer FLAC in title, then by seeders
    def _sort_key(r: Dict) -> Tuple[int, int]:
        title_lower = (r.get("title") or "").lower()
        has_flac = 1 if "flac" in title_lower else 0
        seeders = r.get("seeders", 0) or 0
        return (has_flac, seeders)

    unique.sort(key=_sort_key, reverse=True)

    # Try top results (max 5)
    for r in unique[:5]:
        info_hash = (r.get("infoHash") or "").strip().lower()
        guid = (r.get("guid") or "").strip()

        # Build magnet URI
        if guid.lower().startswith("magnet:"):
            magnet = guid
        elif info_hash:
            dn = (r.get("title") or "").replace(" ", "+")
            magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"
        else:
            continue

        torrent_id = None
        try:
            torrent_id = add_magnet(magnet)
            logger.info(f"[catalog] Added magnet for '{r.get('title', '?')}' → {torrent_id}")

            # Phase 1: wait for file list
            start = time.time()
            selected = False
            while time.time() - start < file_select_wait:
                info = get_torrent_info(torrent_id)
                status = info.get("status", "")

                if status in ("error", "dead", "magnet_error", "virus"):
                    logger.debug(f"[catalog] Bad status: {status}")
                    break

                if status == "waiting_files_selection":
                    files = info.get("files", [])
                    total_bytes = sum(f.get("bytes", 0) for f in files)

                    if total_bytes > max_bytes:
                        gb = total_bytes / 1024 ** 3
                        logger.info(f"[catalog] Too large ({gb:.1f} GB > {max_torrent_gb} GB) — skip")
                        break

                    # Count audio files
                    audio_count = sum(
                        1 for f in files
                        if Path(f.get("path", "")).suffix.lower() in _AUDIO_EXTENSIONS
                    )
                    if audio_count == 0:
                        logger.debug("[catalog] No audio files in torrent")
                        break

                    # Select ALL files for full album
                    select_files(torrent_id, "all")
                    selected = True
                    logger.info(
                        f"[catalog] Selected all files ({audio_count} audio, "
                        f"{total_bytes / 1024**2:.0f} MB)"
                    )
                    break

                if status == "downloaded":
                    selected = True
                    break

                time.sleep(poll_interval)

            if not selected:
                delete_torrent(torrent_id)
                continue

            # Phase 2: wait for download completion
            start = time.time()
            downloaded = False
            while time.time() - start < download_wait:
                info = get_torrent_info(torrent_id)
                status = info.get("status", "")

                if status == "downloaded":
                    downloaded = True
                    break

                if status in ("error", "dead", "magnet_error", "virus"):
                    logger.debug(f"[catalog] Download failed: {status}")
                    break

                progress = info.get("progress", 0)
                logger.debug(f"[catalog] Downloading... {progress}%")
                time.sleep(poll_interval)

            if not downloaded:
                logger.info(f"[catalog] Download timeout for torrent {torrent_id}")
                delete_torrent(torrent_id)
                continue

            # Phase 3: download files
            files = download_torrent_files(torrent_id, output_dir=album_dir, audio_only=True)
            if not files:
                logger.warning("[catalog] No files downloaded after completion")
                delete_torrent(torrent_id)
                continue

            # Match to expected tracklist
            matched = match_files_to_tracklist(files, expected_tracks, artist)
            logger.info(
                f"[catalog] Album '{album_title}': {len(files)} files, "
                f"{len(matched['matched'])} matched, "
                f"{len(matched['missing'])} missing"
            )

            return {
                "success": True,
                "files": [str(f) for f in files],
                "matched": matched["matched"],
                "missing": matched["missing"],
                "bonus": matched["bonus"],
                "torrent_title": r.get("title", ""),
            }

        except Exception as exc:
            logger.warning(f"[catalog] Error with torrent: {exc}")
            if torrent_id:
                delete_torrent(torrent_id)
            continue

<<<<<<< HEAD
    return {"success": False, "error": "All Prowlarr results failed", "files": []}


=======
    fallback = _acquire_album_via_qobuz(artist, album_title, expected_tracks, album_dir)
    if fallback.get("success"):
        return fallback
    return {"success": False, "error": "All Prowlarr results failed", "files": []}


def _acquire_album_via_qobuz(
    artist: str,
    album_title: str,
    expected_tracks: List[Dict[str, Any]],
    album_dir: Path,
) -> Dict[str, Any]:
    """Fallback: acquire album tracks via Qobuz when album torrenting fails."""
    try:
        from oracle.acquirers.qobuz import download as qobuz_download
    except Exception as exc:
        logger.warning(f"[catalog] Qobuz fallback unavailable: {exc}")
        return {"success": False, "error": "Qobuz fallback unavailable", "files": []}

    if not expected_tracks:
        return {"success": False, "error": "No expected tracks for Qobuz fallback", "files": []}

    files: List[Path] = []
    matched: List[Dict[str, Any]] = []
    missing: List[str] = []

    for i, track in enumerate(expected_tracks, start=1):
        title = (track.get("title") or "").strip()
        if not title:
            continue
        result = qobuz_download(artist, title)
        if not result.get("success"):
            missing.append(title)
            continue
        src = Path(result["path"])
        if not src.exists():
            missing.append(title)
            continue
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
        dest = album_dir / f"{i:02d} - {safe_title}{src.suffix.lower()}"
        try:
            if src.resolve() != dest.resolve():
                shutil.move(str(src), str(dest))
        except Exception:
            try:
                shutil.copy2(str(src), str(dest))
            except Exception:
                missing.append(title)
                continue

        files.append(dest)
        matched.append({
            "track_title": title,
            "file_path": str(dest),
            "confidence": 1.0,
            "position": track.get("position", i),
        })

    # Require at least half of the expected tracks to count as a usable fallback album
    min_required = max(1, len(expected_tracks) // 2)
    if len(files) < min_required:
        return {
            "success": False,
            "error": f"Qobuz fallback incomplete ({len(files)}/{len(expected_tracks)})",
            "files": [str(f) for f in files],
            "matched": matched,
            "missing": [t.get("title", "") for t in expected_tracks if t.get("title", "") not in {m['track_title'] for m in matched}],
            "bonus": [],
        }

    logger.info(
        "[catalog] Qobuz fallback succeeded: %s - %s (%d/%d tracks)",
        artist,
        album_title,
        len(files),
        len(expected_tracks),
    )
    return {
        "success": True,
        "files": [str(f) for f in files],
        "matched": matched,
        "missing": [t.get("title", "") for t in expected_tracks if t.get("title", "") not in {m['track_title'] for m in matched}],
        "bonus": [],
        "torrent_title": "",
        "source": "qobuz_fallback",
    }


>>>>>>> fc77b41 (Update workspace state and diagnostics)
def match_files_to_tracklist(
    files: List[Path],
    expected_tracks: List[Dict[str, Any]],
    artist: str,
) -> Dict[str, Any]:
    """Match downloaded audio files to expected MusicBrainz tracklist.

    Returns:
        Dict with 'matched' (list of {track_title, file_path, confidence}),
        'missing' (track titles not found), 'bonus' (files not in tracklist).
    """
    matched: List[Dict[str, Any]] = []
    used_files: set = set()
    used_tracks: set = set()

    for i, track in enumerate(expected_tracks):
        track_title = track.get("title", "")
        target = track_title.lower()
        best_score = 0.0
        best_file: Optional[Path] = None

        for f in files:
            if str(f) in used_files:
                continue
            stem = f.stem.lower()
            # Strip leading track numbers (01, 02-, etc.)
            stem_clean = re.sub(r"^\d{1,3}[\s._-]*", "", stem)
            score = SequenceMatcher(None, target, stem_clean).ratio()
            if score > best_score:
                best_score = score
                best_file = f

        if best_file and best_score >= 0.35:
            matched.append({
                "track_title": track_title,
                "file_path": str(best_file),
                "confidence": round(best_score, 2),
                "position": track.get("position", i + 1),
            })
            used_files.add(str(best_file))
            used_tracks.add(i)

    missing = [
        expected_tracks[i]["title"]
        for i in range(len(expected_tracks))
        if i not in used_tracks
    ]
    bonus = [str(f) for f in files if str(f) not in used_files]

    return {"matched": matched, "missing": missing, "bonus": bonus}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def catalog_lookup(
    artist_name: str,
    types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Look up an artist's verified discography and return structured data.

    Returns:
        Dict with 'artist', 'releases' list.
    """
    artist = lookup_artist(artist_name)
    if not artist:
        return {"error": f"Artist '{artist_name}' not found on MusicBrainz"}

    artist_mbid = artist["id"]
    releases = get_discography(artist_mbid, types=types)

    # Get track listings for each release
    enriched: List[Dict[str, Any]] = []
    for rg in releases:
        tracks_data = get_album_tracks(rg["rgid"])
        track_count = len(tracks_data.get("tracks", []))

        # Skip releases with no tracks (incomplete MB data)
        if track_count == 0:
            continue

        # Check library ownership
        library_check = check_album_in_library(artist_name, rg["title"])

        enriched.append({
            **rg,
            "track_count": track_count,
            "tracks": tracks_data.get("tracks", []),
            "release_mbid": tracks_data.get("release_mbid"),
            "owned_count": library_check["owned_count"],
        })

    return {
        "artist": {
            "name": artist.get("name", artist_name),
            "mbid": artist_mbid,
            "type": artist.get("type", ""),
            "disambiguation": artist.get("disambiguation", ""),
        },
        "releases": enriched,
    }


def catalog_acquire_artist(
    artist_name: str,
    types: Optional[List[str]] = None,
    skip_existing: bool = True,
    dry_run: bool = False,
    limit: int = 0,
    max_torrent_gb: float = 5.0,
    download_wait: int = 120,
    file_select_wait: int = 15,
    poll_interval: int = 3,
    replace_with_hq_album: bool = True,
) -> Dict[str, Any]:
    """Full catalog acquisition workflow for an artist.

    1. Look up discography on MusicBrainz
    2. Store in catalog_releases table
    3. Acquire each album via Prowlarr + Real-Debrid
    """
    lookup = catalog_lookup(artist_name, types=types)
    if "error" in lookup:
        return lookup

    artist_info = lookup["artist"]
    releases = lookup["releases"]
    conn = get_connection()

    # Store in catalog_releases table
    for rel in releases:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO catalog_releases
                   (artist_name, artist_mbid, release_group_mbid, release_mbid,
                    title, release_type, year, track_count, tracks_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    artist_info["name"],
                    artist_info["mbid"],
                    rel["rgid"],
                    rel.get("release_mbid"),
                    rel["title"],
                    rel.get("type", "Album"),
                    rel.get("year"),
                    rel.get("track_count", 0),
                    json.dumps(rel.get("tracks", []), ensure_ascii=False),
                    "skipped" if skip_existing and rel.get("owned_count", 0) > 0 else "pending",
                ),
            )
        except Exception as exc:
            logger.warning(f"[catalog] Failed to store release '{rel['title']}': {exc}")
    conn.commit()

    # Display plan
    pending = [r for r in releases if not (skip_existing and r.get("owned_count", 0) > 0)]
<<<<<<< HEAD
=======
    # Prioritize likely mainline releases first to improve acquisition success.
    pending.sort(
        key=lambda r: (
            1 if _LOW_PRIORITY_TITLE_RE.search(r.get("title", "")) else 0,
            -(r.get("track_count") or 0),
            -(r.get("year") or 0),
            r.get("title", ""),
        )
    )
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    if limit > 0:
        pending = pending[:limit]

    if dry_run:
        conn.close()
        return {
            "artist": artist_info,
            "total_releases": len(releases),
            "to_acquire": len(pending),
            "releases": releases,
            "dry_run": True,
        }

    # Acquire albums
    acquired = 0
    failed = 0
    results: List[Dict[str, Any]] = []

    for rel in pending:
        logger.info(f"[catalog] Acquiring: {artist_info['name']} - {rel['title']} ({rel.get('year', '?')})")

        result = acquire_album(
            artist=artist_info["name"],
            album_title=rel["title"],
            expected_tracks=rel.get("tracks", []),
            max_torrent_gb=max_torrent_gb,
            download_wait=download_wait,
            file_select_wait=file_select_wait,
            poll_interval=poll_interval,
        )

        if result["success"]:
            full_match = not result.get("missing")
            hq_album = _is_high_quality_album([Path(p) for p in result.get("files", [])])
            replacement = None
            if replace_with_hq_album and full_match and hq_album:
                replacement = _promote_album_and_replace_existing(
                    artist=artist_info["name"],
                    album_title=rel["title"],
                    year=rel.get("year"),
                    matched=result.get("matched", []),
                )
                result["replacement"] = replacement
                result["files"] = [m["file_path"] for m in result.get("matched", [])]
                logger.info(
                    "[catalog] Promoted HQ album to library: %s (promoted=%s replaced=%s)",
                    rel["title"],
                    replacement.get("promoted", 0),
                    replacement.get("replaced_existing", 0),
                )
            acquired += 1
            conn.execute(
                """UPDATE catalog_releases SET status = 'acquired', acquired_at = datetime('now')
                   WHERE release_group_mbid = ?""",
                (rel["rgid"],),
            )
        else:
            failed += 1
            conn.execute(
                """UPDATE catalog_releases SET status = 'failed', error = ?
                   WHERE release_group_mbid = ?""",
                (result.get("error", "unknown"), rel["rgid"]),
            )
        conn.commit()

        results.append({
            "title": rel["title"],
            "year": rel.get("year"),
            **result,
        })

    conn.close()

    return {
        "artist": artist_info,
        "total_releases": len(releases),
        "acquired": acquired,
        "failed": failed,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_lookup(data: Dict[str, Any]) -> None:
    """Print a formatted discography lookup."""
    if "error" in data:
        print(f"Error: {data['error']}")
        return

    artist = data["artist"]
    releases = data["releases"]

    print(f"\n{'=' * 60}")
    print(f"  {artist['name']}")
    if artist.get("disambiguation"):
        print(f"  ({artist['disambiguation']})")
    print(f"  MBID: {artist['mbid']}")
    print(f"{'=' * 60}\n")

    for i, rel in enumerate(releases, 1):
        year = rel.get("year") or "????"
        rtype = rel.get("type", "Album")
        tracks = rel.get("track_count", 0)
        owned = rel.get("owned_count", 0)

        status = ""
        if owned > 0:
            pct = owned * 100 // max(tracks, 1)
            status = f" [{owned}/{tracks} owned ({pct}%)]"
        else:
            status = " [NOT OWNED]"

        print(f"  [{i:2d}] {year} | {rtype:6s} | {rel['title']}")
        print(f"       {tracks} tracks{status}")

        # Show track listing
        for t in rel.get("tracks", []):
            pos = t.get("position", "?")
            title = t.get("title", "?")
            dur_ms = t.get("duration_ms")
            dur = f" ({dur_ms // 60000}:{(dur_ms % 60000) // 1000:02d})" if dur_ms else ""
            print(f"         {pos:2}. {title}{dur}")
        print()


def display_acquire_results(data: Dict[str, Any]) -> None:
    """Print acquisition results."""
    if "error" in data:
        print(f"Error: {data['error']}")
        return

    artist = data.get("artist", {})
    print(f"\n{artist.get('name', '?')} — Catalog Acquisition")
    print(f"{'=' * 50}")

    if data.get("dry_run"):
        releases = data.get("releases", [])
        to_acquire = data.get("to_acquire", 0)
        print(f"Total releases: {len(releases)}")
        print(f"To acquire: {to_acquire}\n")

        for rel in releases:
            owned = rel.get("owned_count", 0)
            tracks = rel.get("track_count", 0)
            year = rel.get("year") or "????"
            skip = " [SKIP — already owned]" if owned > 0 else ""
            print(f"  {year} | {rel['title']} ({tracks} tracks){skip}")
        return

    acquired = data.get("acquired", 0)
    failed = data.get("failed", 0)
    print(f"Acquired: {acquired}, Failed: {failed}\n")

    for r in data.get("results", []):
        year = r.get("year") or "????"
        status = "OK" if r.get("success") else "FAIL"
        print(f"  [{status}] {year} | {r.get('title', '?')}")
        if r.get("success"):
            print(f"       {len(r.get('matched', []))} matched, "
                  f"{len(r.get('missing', []))} missing, "
                  f"{len(r.get('bonus', []))} bonus")
            replacement = r.get("replacement")
            if replacement:
                print(
                    "       promoted={promoted} replaced={replaced_existing} target={target_dir}".format(
                        **replacement
                    )
                )
            if r.get("missing"):
                for m in r["missing"]:
                    print(f"         MISSING: {m}")
        else:
            print(f"       Error: {r.get('error', '?')}")
