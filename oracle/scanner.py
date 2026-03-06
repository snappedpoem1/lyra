"""Library scanner for Lyra Oracle."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import shutil
import time

from dotenv import load_dotenv
from mutagen import File as MutagenFile
from tqdm import tqdm

from oracle.config import LIBRARY_BASE, QUARANTINE_PATH as CONFIG_QUARANTINE_PATH
from oracle.db.schema import get_connection, get_content_hash_fast, get_track_id, get_write_mode
from oracle.name_cleaner import clean_artist, clean_title_str

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUARANTINE_PATH = CONFIG_QUARANTINE_PATH
AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aiff", ".aac", ".wma"}

DEFAULT_LIBRARY_PATH = LIBRARY_BASE
PLACEHOLDER_PATH_MARKERS = (
    "\\your\\music\\path",
    "\\your music path",
    "your\\music\\path",
    "your music path",
)


def _build_missing_library_hint(library_path: str, resolved_path: Path) -> str:
    raw = str(library_path).strip().lower().replace("/", "\\")

    hint_parts = []
    if any(marker in raw for marker in PLACEHOLDER_PATH_MARKERS):
        hint_parts.append("The value looks like a placeholder example path.")

    if DEFAULT_LIBRARY_PATH.exists():
        hint_parts.append(f"Try --library \"{DEFAULT_LIBRARY_PATH}\".")

    if not hint_parts:
        return f"Library path not found: {resolved_path}"

    return f"Library path not found: {resolved_path}. {' '.join(hint_parts)}"


def _resolve_library_root(library_path: str) -> Path:
    raw = str(library_path).strip().lower().replace("/", "\\")
    if any(marker in raw for marker in PLACEHOLDER_PATH_MARKERS) and DEFAULT_LIBRARY_PATH.exists():
        print(f"INFO: Placeholder library path detected; redirecting to {DEFAULT_LIBRARY_PATH}")
        return DEFAULT_LIBRARY_PATH.resolve()
    return Path(library_path).expanduser().resolve()


def normalize_text(text: str) -> str:
    return text.strip().lower()


def _deep_clean_title(title: str) -> str:
    """Use canonical title normalization from name_cleaner."""
    return clean_title_str(title)


def get_default_metadata(file_path: Path) -> Dict[str, str]:
    name = file_path.stem
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return {"artist": artist.strip(), "title": _deep_clean_title(title)}
    return {"title": _deep_clean_title(name)}


def extract_metadata(file_path: Path) -> Dict[str, str]:
    meta = get_default_metadata(file_path)
    try:
        audio_easy = MutagenFile(str(file_path), easy=True)
        if audio_easy and audio_easy.tags:
            if "artist" in audio_easy.tags and audio_easy.tags["artist"]:
                meta["artist"] = audio_easy.tags["artist"][0]
            if "title" in audio_easy.tags and audio_easy.tags["title"]:
                meta["title"] = _deep_clean_title(audio_easy.tags["title"][0])
            if "album" in audio_easy.tags and audio_easy.tags["album"]:
                meta["album"] = audio_easy.tags["album"][0]
            if "date" in audio_easy.tags and audio_easy.tags["date"]:
                meta["year"] = audio_easy.tags["date"][0]
            if "tracknumber" in audio_easy.tags and audio_easy.tags["tracknumber"]:
                raw_tn = str(audio_easy.tags["tracknumber"][0]).split("/")[0].strip()
                if raw_tn.isdigit():
                    meta["track_number"] = raw_tn
            if "discnumber" in audio_easy.tags and audio_easy.tags["discnumber"]:
                raw_dn = str(audio_easy.tags["discnumber"][0]).split("/")[0].strip()
                if raw_dn.isdigit():
                    meta["disc_number"] = raw_dn

        duration_source = audio_easy
        if not (duration_source and duration_source.info and getattr(duration_source.info, "length", None)):
            # Some files fail with easy=True parsing but still expose duration normally.
            duration_source = MutagenFile(str(file_path), easy=False)

        if duration_source and duration_source.info and getattr(duration_source.info, "length", None):
            meta["duration"] = str(float(duration_source.info.length))
    except Exception:
        pass

    if "title" in meta:
        meta["title"] = _deep_clean_title(meta["title"])

    # Strip feat. / ft. from artist tag â€” store only the primary artist
    if "artist" in meta:
        meta["artist"], _ = clean_artist(meta["artist"])

    return meta


def _sanitize_duration(value) -> float | None:
    """Normalize parsed duration value; return None when invalid."""
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def quarantine_file(file_path: Path) -> Tuple[bool, str]:
    QUARANTINE_PATH.mkdir(parents=True, exist_ok=True)
    target = QUARANTINE_PATH / file_path.name
    suffix = 1
    while target.exists():
        target = QUARANTINE_PATH / f"{file_path.stem}_{suffix}{file_path.suffix}"
        suffix += 1

    try:
        shutil.copy2(str(file_path), str(target))
        if file_path.stat().st_size == target.stat().st_size:
            file_path.unlink()
            return True, str(target)
    except Exception as exc:
        return False, str(exc)

    return False, "Copy verification failed"


def _is_under_root(filepath: str, root: Path) -> bool:
    try:
        fp = Path(filepath).resolve()
        rr = root.resolve()
        return str(fp).lower().startswith(str(rr).lower())
    except Exception:
        return str(filepath).lower().startswith(str(root).lower())


def scan_library(library_path: str, limit: int = 0) -> Dict[str, int]:
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to scan.")
        return {"scanned": 0, "added": 0, "updated": 0, "quarantined": 0, "errors": 1}

    root = _resolve_library_root(library_path)
    if not root.exists():
        raise FileNotFoundError(_build_missing_library_hint(library_path, root))

    files: List[Path] = []
    for ext in AUDIO_EXTS:
        files.extend(root.rglob(f"*{ext}"))

    if limit and limit > 0:
        files = files[:limit]

    stats = {"scanned": 0, "added": 0, "updated": 0, "quarantined": 0, "errors": 0}
    seen_paths = set()

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    for file_path in tqdm(files, desc="Scanning", unit="file"):
        stats["scanned"] += 1
        seen_paths.add(str(file_path))

        try:
            if file_path.stat().st_size == 0:
                ok, detail = quarantine_file(file_path)
                if ok:
                    stats["quarantined"] += 1
                else:
                    stats["errors"] += 1
                continue

            content_hash = get_content_hash_fast(file_path)
            track_id = get_track_id(content_hash)
            meta = extract_metadata(file_path)
            now = time.time()

            cursor.execute(
                "SELECT track_id FROM tracks WHERE filepath = ?",
                (str(file_path),)
            )
            existing = cursor.fetchone()

            if existing:
                duration_value = _sanitize_duration(meta.get("duration"))
                tn = int(meta["track_number"]) if meta.get("track_number") else None
                dn = int(meta["disc_number"]) if meta.get("disc_number") else None
                cursor.execute(
                    """
                    UPDATE tracks
                    SET artist = ?, title = ?, album = ?, year = ?, genre = ?,
                        duration = COALESCE(?, duration),
                        track_number = COALESCE(?, track_number),
                        disc_number = COALESCE(?, disc_number),
                        content_hash = ?, last_seen_at = ?, updated_at = ?, status = 'active'
                    WHERE filepath = ?
                    """,
                    (
                        meta.get("artist"),
                        meta.get("title"),
                        meta.get("album"),
                        meta.get("year"),
                        meta.get("genre"),
                        duration_value,
                        tn,
                        dn,
                        content_hash,
                        now,
                        now,
                        str(file_path),
                    )
                )
                stats["updated"] += 1
            else:
                duration_value = _sanitize_duration(meta.get("duration"))
                tn = int(meta["track_number"]) if meta.get("track_number") else None
                dn = int(meta["disc_number"]) if meta.get("disc_number") else None
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO tracks (
                        track_id, filepath, artist, title, album, year, genre, duration,
                        track_number, disc_number,
                        content_hash, last_seen_at, status, added_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        track_id,
                        str(file_path),
                        meta.get("artist"),
                        meta.get("title"),
                        meta.get("album"),
                        meta.get("year"),
                        meta.get("genre"),
                        duration_value,
                        tn,
                        dn,
                        content_hash,
                        now,
                        now,
                        now,
                    )
                )
                stats["added"] += 1

        except Exception as exc:
            import logging
            logging.getLogger("scanner").warning("Scan error on %s: %s", file_path.name, exc)
            stats["errors"] += 1

    cursor.execute("PRAGMA table_info(tracks)")
    columns = {row[1] for row in cursor.fetchall()}
    track_id_col = "track_id" if "track_id" in columns else "id"
    if track_id_col not in {"track_id", "id"}:
        raise RuntimeError(f"Unexpected track identifier column: {track_id_col}")

    if track_id_col == "track_id":
        cursor.execute("SELECT track_id, filepath FROM tracks WHERE status != 'missing'")
    else:
        cursor.execute("SELECT id, filepath FROM tracks WHERE status != 'missing'")
    for track_id, filepath in cursor.fetchall():
        if not _is_under_root(filepath, root):
            continue
        if filepath not in seen_paths:
            if track_id_col == "track_id":
                cursor.execute(
                    "UPDATE tracks SET status = 'missing', updated_at = ? WHERE track_id = ?",
                    (time.time(), track_id),
                )
            else:
                cursor.execute(
                    "UPDATE tracks SET status = 'missing', updated_at = ? WHERE id = ?",
                    (time.time(), track_id),
                )

    conn.commit()
    conn.close()

    return stats


def scan_paths(paths: Iterable[Path]) -> Dict[str, object]:
    """Scan a bounded list of file paths without walking the whole library tree."""
    if get_write_mode() != "apply_allowed":
        print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to scan.")
        return {
            "scanned": 0,
            "added": 0,
            "updated": 0,
            "quarantined": 0,
            "errors": 1,
            "track_ids": [],
        }

    files = [Path(p) for p in paths if Path(p).is_file() and Path(p).suffix.lower() in AUDIO_EXTS]
    stats: Dict[str, object] = {
        "scanned": 0,
        "added": 0,
        "updated": 0,
        "quarantined": 0,
        "errors": 0,
        "track_ids": [],
    }

    if not files:
        return stats

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    for file_path in files:
        stats["scanned"] = int(stats["scanned"]) + 1
        try:
            if file_path.stat().st_size == 0:
                ok, _ = quarantine_file(file_path)
                if ok:
                    stats["quarantined"] = int(stats["quarantined"]) + 1
                else:
                    stats["errors"] = int(stats["errors"]) + 1
                continue

            content_hash = get_content_hash_fast(file_path)
            track_id = get_track_id(content_hash)
            meta = extract_metadata(file_path)
            now = time.time()

            cursor.execute("SELECT track_id FROM tracks WHERE filepath = ?", (str(file_path),))
            existing = cursor.fetchone()

            if existing:
                duration_value = _sanitize_duration(meta.get("duration"))
                tn = int(meta["track_number"]) if meta.get("track_number") else None
                dn = int(meta["disc_number"]) if meta.get("disc_number") else None
                cursor.execute(
                    """
                    UPDATE tracks
                    SET artist = ?, title = ?, album = ?, year = ?, genre = ?,
                        duration = COALESCE(?, duration),
                        track_number = COALESCE(?, track_number),
                        disc_number = COALESCE(?, disc_number),
                        content_hash = ?, last_seen_at = ?, updated_at = ?, status = 'active'
                    WHERE filepath = ?
                    """,
                    (
                        meta.get("artist"),
                        meta.get("title"),
                        meta.get("album"),
                        meta.get("year"),
                        meta.get("genre"),
                        duration_value,
                        tn,
                        dn,
                        content_hash,
                        now,
                        now,
                        str(file_path),
                    ),
                )
                stats["updated"] = int(stats["updated"]) + 1
            else:
                duration_value = _sanitize_duration(meta.get("duration"))
                tn = int(meta["track_number"]) if meta.get("track_number") else None
                dn = int(meta["disc_number"]) if meta.get("disc_number") else None
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO tracks (
                        track_id, filepath, artist, title, album, year, genre, duration,
                        track_number, disc_number,
                        content_hash, last_seen_at, status, added_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        track_id,
                        str(file_path),
                        meta.get("artist"),
                        meta.get("title"),
                        meta.get("album"),
                        meta.get("year"),
                        meta.get("genre"),
                        duration_value,
                        tn,
                        dn,
                        content_hash,
                        now,
                        now,
                        now,
                    ),
                )
                stats["added"] = int(stats["added"]) + 1

            cast_ids = stats["track_ids"]
            if isinstance(cast_ids, list):
                cast_ids.append(track_id)
        except Exception as exc:
            import logging
            logging.getLogger("scanner").warning("Scan error on %s: %s", file_path.name, exc)
            stats["errors"] = int(stats["errors"]) + 1

    conn.commit()
    conn.close()
    return stats


def _main() -> None:
    load_dotenv(override=True)
    import argparse

    parser = argparse.ArgumentParser(description="Scan library")
    parser.add_argument("--library", required=True, help="Library path to scan")
    parser.add_argument("--limit", type=int, default=0, help="Limit files")
    args = parser.parse_args()

    results = scan_library(args.library, limit=args.limit)
    print(results)


if __name__ == "__main__":
    _main()
