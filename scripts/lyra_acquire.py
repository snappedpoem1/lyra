"""
lyra_acquire.py — Tiered Acquisition Engine
=============================================
Real-Debrid (via Hunter/Prowlarr) first, SpotiFLAC fallback.
Supports artist filtering, whole-artist mode, full discography
mode, liked-songs folder linking, and dry-run.

Usage:
    python lyra_acquire.py --artist "Brand New" --limit 10
    python lyra_acquire.py --artist "Coheed and Cambria" --whole-artist
    python lyra_acquire.py --artist "Coheed and Cambria" --discography
    python lyra_acquire.py --link-liked
    python lyra_acquire.py --dry-run --limit 20

Tier 1: Prowlarr → Real-Debrid (album-level FLAC torrents)
Tier 2: SpotiFLAC (track-level FLAC via Tidal/Qobuz/Amazon)
"""

from __future__ import annotations

import argparse
<<<<<<< HEAD
=======
import atexit
>>>>>>> fc77b41 (Update workspace state and diagnostics)
import logging
import os
import re
import shutil
import subprocess
import sqlite3
import sys
<<<<<<< HEAD
import time
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

<<<<<<< HEAD
from oracle.config import get_connection, LIBRARY_BASE, LYRA_DB_PATH
=======
from oracle.config import get_connection, LIBRARY_BASE
>>>>>>> fc77b41 (Update workspace state and diagnostics)

logger = logging.getLogger("lyra.acquire")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)

# Audio extensions we care about when unpacking RD results
AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma", ".alac"}
<<<<<<< HEAD
=======
SPOTIFY_MAX_RETRY_AFTER_SECONDS = int(
    os.getenv("LYRA_SPOTIFY_MAX_RETRY_AFTER_SECONDS", "120") or "120"
)
ACQUIRE_LOCK_PATH = Path("logs") / "lyra_acquire.lock"
>>>>>>> fc77b41 (Update workspace state and diagnostics)

# ──────────────────────────────────────────────────────────────
# DB Helpers
# ──────────────────────────────────────────────────────────────

def _queue_columns() -> set[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(acquisition_queue)")
    cols = {row[1] for row in cur.fetchall()}
    conn.close()
    return cols


def fetch_pending_targets(
    limit: int,
    artist: str | None = None,
    whole_artist: bool = False,
) -> List[Tuple[int, str, str, str, str]]:
    """Return (id, artist, title, album, spotify_uri) tuples from queue."""
    conn = get_connection()
    cur = conn.cursor()

    if artist:
        if whole_artist:
            cur.execute(
                """SELECT id, artist, title, album, spotify_uri
                   FROM acquisition_queue
                   WHERE status = 'pending' AND lower(artist) = lower(?)
                   ORDER BY priority_score DESC, play_count DESC, id ASC""",
                (artist,),
            )
        else:
            cur.execute(
                """SELECT id, artist, title, album, spotify_uri
                   FROM acquisition_queue
                   WHERE status = 'pending' AND lower(artist) = lower(?)
                   ORDER BY priority_score DESC, play_count DESC, id ASC
                   LIMIT ?""",
                (artist, limit),
            )
    else:
        cur.execute(
            """SELECT id, artist, title, album, spotify_uri
               FROM acquisition_queue
               WHERE status = 'pending'
               ORDER BY priority_score DESC, play_count DESC, id ASC
               LIMIT ?""",
            (limit,),
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def update_status(queue_id: int, status: str, error: str | None = None) -> None:
    cols = _queue_columns()
    conn = get_connection()
    cur = conn.cursor()
    parts = ["status = ?"]
    params: list = [status]

    if "error" in cols:
        parts.append("error = ?")
        params.append(error)

    if "completed_at" in cols:
        parts.append(
            "completed_at = CASE WHEN ? IN ('complete','failed','skipped') "
            "THEN datetime('now') ELSE completed_at END"
        )
        params.append(status)

    params.append(queue_id)
    cur.execute(f"UPDATE acquisition_queue SET {', '.join(parts)} WHERE id = ?", tuple(params))
    conn.commit()
    conn.close()


def _check_local_ownership(artist: str, title: str) -> bool:
    """Fuzzy check if a track already exists in the local library."""
    conn = get_connection()
    cur = conn.cursor()
    norm_a = _normalize(artist)
    norm_t = _normalize(title)
    cur.execute(
        """SELECT COUNT(*) FROM tracks
           WHERE status = 'active'
             AND LOWER(artist) LIKE ? AND LOWER(title) LIKE ?""",
        (f"%{norm_a}%", f"%{norm_t}%"),
    )
    found = cur.fetchone()[0] > 0
    conn.close()
    return found


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s*\(feat\.?.*?\)", "", text)
    text = re.sub(r"\s*\[feat\.?.*?\]", "", text)
    text = re.sub(r"\s*ft\.?\s+.*$", "", text)
    text = re.sub(r"\s*-\s*(remaster(ed)?|deluxe|bonus|anniversary).*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_artist_identity(name: str) -> str:
    """Normalize artist names for identity matching (not fuzzy containment)."""
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    # Ignore a leading "the" to reduce common catalog alias mismatches.
    if s.startswith("the "):
        s = s[4:]
    return s


<<<<<<< HEAD
=======
def _spotify_call(callable_obj, *args, **kwargs):
    """Call Spotify API and fail fast on extreme rate-limit retry windows."""
    try:
        return callable_obj(*args, **kwargs)
    except Exception as exc:
        msg = str(exc)
        retry_match = re.search(r"Retry will occur after:\s*(\d+)\s*s", msg, re.IGNORECASE)
        if retry_match:
            retry_after = int(retry_match.group(1))
            if retry_after > SPOTIFY_MAX_RETRY_AFTER_SECONDS:
                logger.warning(
                    "Spotify rate-limit retry (%ss) exceeds cap (%ss); skipping call.",
                    retry_after,
                    SPOTIFY_MAX_RETRY_AFTER_SECONDS,
                )
                return None
        raise


def _acquire_run_lock() -> None:
    """Ensure only one lyra_acquire process runs at a time."""
    ACQUIRE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ACQUIRE_LOCK_PATH.exists():
        try:
            pid = int(ACQUIRE_LOCK_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if pid > 0:
            try:
                os.kill(pid, 0)
                raise RuntimeError(f"lyra_acquire already running (pid={pid})")
            except OSError:
                pass
    ACQUIRE_LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _release_run_lock() -> None:
    try:
        if ACQUIRE_LOCK_PATH.exists():
            ACQUIRE_LOCK_PATH.unlink()
    except Exception:
        pass


>>>>>>> fc77b41 (Update workspace state and diagnostics)
# ──────────────────────────────────────────────────────────────
# TIER 1 — Real-Debrid via Hunter (album-level FLAC torrents)
# ──────────────────────────────────────────────────────────────

# Quality waterfall: try highest first, fall back progressively
QUALITY_TIERS = ["FLAC", "MP3 320", ""]


def _build_rd_search_queries(
    artist: str,
    album: str | None,
    title: str | None,
    quality_preference: str = "FLAC",
) -> list[str]:
    """Build a list of Prowlarr search queries, best quality first.

    Order (for each quality tier):
      1. Discography
      2. Album-level
      3. Track-level fallback

    Quality tiers: FLAC → MP3 320 → any format.
    If quality_preference is not FLAC, the tiers start from that level.
    """
    # Build quality tiers starting from the user's preference
    start_idx = 0
    for i, tier in enumerate(QUALITY_TIERS):
        if tier.upper() == quality_preference.upper():
            start_idx = i
            break
    tiers = QUALITY_TIERS[start_idx:]

    queries: list[str] = []
    seen: set[str] = set()

    for quality_tag in tiers:
        suffix = f" {quality_tag}" if quality_tag else ""
        candidates = [f"{artist} discography{suffix}"]
        if album:
            candidates.append(f"{artist} {album}{suffix}")
        if title:
            candidates.append(f"{artist} {title}{suffix}")

        for q in candidates:
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                queries.append(q)

    return queries


def _extract_audio_files(download_dir: Path) -> List[Path]:
    """Recursively find all audio files under a directory."""
    found: List[Path] = []
    for root, _dirs, files in os.walk(download_dir):
        for f in files:
            if Path(f).suffix.lower() in AUDIO_EXTS:
                found.append(Path(root) / f)
    return found


def acquire_via_realdebrid(
    artist: str,
    album: str | None,
    title: str | None,
    dry_run: bool = False,
    quality_preference: str = "FLAC",
) -> dict:
    """
    Tier 1: Search Prowlarr → check RD cache → download.

    Returns:
        {"status": "complete"|"failed"|"no_results", "files": [...], "error": ...}
    """
    from oracle.hunter import Hunter

    queries = _build_rd_search_queries(artist, album, title, quality_preference)

    if dry_run:
        logger.info(f"  🔎 TIER 1 (Real-Debrid): {len(queries)} queries across quality tiers")
        for q in queries:
            logger.info(f"     • {q}")
        logger.info(f"  🧪 DRY RUN: would try {len(queries)} query(ies)")
        return {"status": "dry_run", "queries": queries}

    try:
        hunter = Hunter()
        targets = []
<<<<<<< HEAD
        used_query = None
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        for q in queries:
            logger.info(f"  🔎 TIER 1 (Real-Debrid): searching [{q}]")
            hits = hunter.hunt(q, quality_preference=quality_preference)
            if not hits:
                continue
            # Only accept results that are alive (seeded) or already cached on RD
            viable = [h for h in hits if h.get("seeders", 0) > 0 or h.get("is_cached")]
            if viable:
                targets = viable
<<<<<<< HEAD
                used_query = q
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                break
            else:
                logger.info(f"  ⚠️  All {len(hits)} results have 0 seeders and not cached — trying next query")

        if not targets:
            logger.info("  ⚠️  No Prowlarr results — falling through to Tier 2")
            return {"status": "no_results"}

        # Take the best-ranked target
        best = targets[0]
        cached_tag = "⚡ CACHED" if best.get("is_cached") else ""
        logger.info(
            f"  → Best match: {best['title']} "
            f"[{best['quality']}] {best.get('seeders', 0)} seeders "
            f"{cached_tag} (priority {best['priority']:.2f})"
        )

        result = hunter.acquire(best)

        if result.get("status") == "completed":
            file_path = result.get("file_path")
            logger.info(f"  ✅ RD download complete: {file_path}")

            # Move audio files to library under Artist/Album structure
            moved = _organize_rd_download(Path(file_path) if file_path else None, artist, album)
            return {"status": "complete", "files": moved, "source": "real-debrid"}
        elif result.get("status") == "pending":
            tid = result.get("torrent_id")
            logger.info(f"  ⏳ RD torrent {tid} still downloading — will check back later")
            return {"status": "rd_pending", "torrent_id": tid, "title": best["title"]}
        else:
            err = result.get("error", "unknown")
            logger.warning(f"  ⚠️  RD acquisition failed: {err}")
            return {"status": "failed", "error": err}

    except Exception as exc:
        logger.warning(f"  ⚠️  Tier 1 exception: {exc}")
        return {"status": "failed", "error": str(exc)}


def _organize_rd_download(
    downloaded_path: Path | None,
    artist: str,
    album: str | None,
) -> List[Path]:
    """Move downloaded files into Artist/Album structure under LIBRARY_BASE."""
    if not downloaded_path or not downloaded_path.exists():
        # Check downloads/ and staging/ for recent audio files
        for search_dir in [Path("downloads"), Path("staging")]:
            search_dir = Path(__file__).parent / search_dir
            if search_dir.exists():
                audio = _extract_audio_files(search_dir)
                if audio:
                    return _move_to_library(audio, artist, album)
        return []

    if downloaded_path.is_dir():
        audio = _extract_audio_files(downloaded_path)
    elif downloaded_path.suffix.lower() in AUDIO_EXTS:
        audio = [downloaded_path]
    else:
        # Could be an archive — check the parent dir
        audio = _extract_audio_files(downloaded_path.parent)

    return _move_to_library(audio, artist, album)


# Quality rank for extension-based comparison (higher = better)
_QUALITY_RANK: Dict[str, int] = {
    ".flac": 100, ".alac": 95, ".wav": 90,
    ".opus": 60, ".ogg": 55, ".aac": 50, ".m4a": 50,
    ".mp3": 40, ".wma": 30,
}


def _ext_quality(path: Path) -> int:
    """Return a numeric quality rank for an audio file based on extension."""
    return _QUALITY_RANK.get(path.suffix.lower(), 0)


def _find_existing_match(dest_dir: Path, stem: str) -> Path | None:
    """Find an existing file in dest_dir whose stem matches (ignoring quality suffix).

    Matches by normalized stem: strips leading track numbers and timestamps,
    then compares case-insensitively.
    """
    # Normalize: remove leading "01 " or "01. " or "A1. " prefixes
    norm = re.sub(r"^[A-Za-z]?\d+[\.\-\s]+", "", stem).strip().lower()
    if not norm:
        norm = stem.lower()

    for existing in dest_dir.iterdir():
        if not existing.is_file():
            continue
        if existing.suffix.lower() not in AUDIO_EXTS:
            continue
        exist_stem = re.sub(r"^[A-Za-z]?\d+[\.\-\s]+", "", existing.stem).strip().lower()
        # Also strip timestamp suffixes we may have added before (e.g. _1771376004)
        exist_stem = re.sub(r"_\d{10}$", "", exist_stem)
        if not exist_stem:
            exist_stem = existing.stem.lower()
        if exist_stem == norm:
            return existing
    return None


def _move_to_library(files: List[Path], artist: str, album: str | None) -> List[Path]:
    """Move audio files to LIBRARY_BASE/Artist/Album/.

    Quality upgrade: if a lower-quality version already exists in the
    destination, replace it with the higher-quality file.
    """
    if not files:
        return []

    safe_artist = re.sub(r'[<>:"/\\|?*]', "_", artist)
    safe_album = re.sub(r'[<>:"/\\|?*]', "_", album) if album else "Singles"
    dest_dir = LIBRARY_BASE / safe_artist / safe_album
    dest_dir.mkdir(parents=True, exist_ok=True)

    moved: List[Path] = []
    for f in files:
        new_quality = _ext_quality(f)
        target = dest_dir / f.name

        # Check if an identical filename exists
        if target.exists():
            old_quality = _ext_quality(target)
            if new_quality > old_quality:
                logger.info(f"    ⬆️  Upgrading {target.name} ({target.suffix} → {f.suffix})")
                target.unlink()
            elif new_quality == old_quality:
                # Same quality, same name — skip (already have it)
                logger.debug(f"    ⏭️  Already have: {target.name}")
                f.unlink(missing_ok=True)
                continue
            else:
                # New file is lower quality — skip
                logger.debug(f"    ⏭️  Keeping higher quality: {target.name}")
                f.unlink(missing_ok=True)
                continue

        # Check for a different-extension match (e.g. track.mp3 → track.flac)
        if not target.exists():
            existing = _find_existing_match(dest_dir, f.stem)
            if existing:
                old_quality = _ext_quality(existing)
                if new_quality > old_quality:
                    logger.info(
                        f"    ⬆️  Replacing {existing.name} with {f.name} "
                        f"(quality {old_quality} → {new_quality})"
                    )
                    existing.unlink()
                elif new_quality <= old_quality:
                    logger.debug(f"    ⏭️  Already have equal/better: {existing.name}")
                    f.unlink(missing_ok=True)
                    continue

        try:
            final = dest_dir / f.name
            shutil.move(str(f), str(final))
            moved.append(final)
            logger.info(f"    📂 {final}")
        except Exception as exc:
            logger.warning(f"    ⚠️  Move failed for {f.name}: {exc}")

    return moved


# ──────────────────────────────────────────────────────────────
# TIER 2 — SpotiFLAC fallback (track-level FLAC via Tidal/Qobuz)
# ──────────────────────────────────────────────────────────────

def _resolve_spotiflac_invocation() -> List[str] | None:
    launcher = shutil.which("spotiflac")
    if launcher:
        return [launcher]

    check_cmd = [sys.executable, "-m", "SpotiFLAC.SpotiFLAC", "--help"]
    probe = subprocess.run(check_cmd, capture_output=True, text=True)
    if probe.returncode == 0:
        return [sys.executable, "-m", "SpotiFLAC.SpotiFLAC"]

    return None


def acquire_via_spotiflac(
    spotify_uri: str,
    artist: str,
    title: str,
    dry_run: bool = False,
) -> dict:
    """
    Tier 2: Download individual track via SpotiFLAC using Spotify URI.

    Returns:
        {"status": "complete"|"failed"|"skipped", "error": ...}
    """
    if not spotify_uri:
        return {"status": "skipped", "error": "missing spotify_uri"}

    spotiflac_cmd = _resolve_spotiflac_invocation()
    if not spotiflac_cmd:
        return {"status": "failed", "error": "SpotiFLAC not installed (pip install SpotiFLAC)"}

    cmd = [*spotiflac_cmd, spotify_uri, str(LIBRARY_BASE)]
    logger.info(f"  🔎 TIER 2 (SpotiFLAC): {artist} - {title}")

    if dry_run:
        logger.info(f"  🧪 DRY RUN: {' '.join(cmd)}")
        return {"status": "dry_run", "cmd": " ".join(cmd)}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logger.info("  ✅ SpotiFLAC download complete")
            return {"status": "complete", "source": "spotiflac"}
        else:
            err = (result.stderr or result.stdout or "download failed").strip()[:500]
            logger.warning(f"  ❌ SpotiFLAC failed: {err}")
            return {"status": "failed", "error": err}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "SpotiFLAC timeout (120s)"}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


# ──────────────────────────────────────────────────────────────
# Tiered Waterfall — orchestrates RD → SpotiFLAC
# ──────────────────────────────────────────────────────────────

def acquire_track(
    queue_id: int,
    artist: str,
    title: str,
    album: str | None,
    spotify_uri: str | None,
    dry_run: bool = False,
    quality_preference: str = "FLAC",
) -> str | tuple:
    """
    Try Tier 1 (Real-Debrid) first, fall back to Tier 2 (SpotiFLAC).

    Returns:
        'complete', 'failed', 'dry_run', 'skipped'
        OR  ('rd_pending', rd_info_dict) if RD torrent still downloading
            AND SpotiFLAC also unavailable.
    """
    artist_name = artist or "Unknown Artist"
    track_title = title or "Unknown Title"

    logger.info(f"🎯 ACQUIRING: {artist_name} — {track_title}")

    if not dry_run:
        update_status(queue_id, "downloading")

    # ── TIER 1: Real-Debrid (album-level preferred) ──
    rd_result = acquire_via_realdebrid(
        artist_name, album, track_title,
        dry_run=dry_run, quality_preference=quality_preference,
    )

    if rd_result["status"] == "complete":
        if not dry_run:
            update_status(queue_id, "complete")
        return "complete"

    if rd_result["status"] == "dry_run":
        return "dry_run"

    rd_is_pending = rd_result["status"] == "rd_pending"

    # ── TIER 2: SpotiFLAC (track-level fallback) ──
    if spotify_uri:
        sf_result = acquire_via_spotiflac(spotify_uri, artist_name, track_title, dry_run=dry_run)

        if sf_result["status"] == "complete":
            if not dry_run:
                update_status(queue_id, "complete")
            # SpotiFLAC handled it — still pass pending RD info so harvest can
            # optionally upgrade to FLAC later if the torrent finishes
            if rd_is_pending:
                return "rd_pending", rd_result
            return "complete"

        if sf_result["status"] == "dry_run":
            return "dry_run"

    # Both tiers failed / no Spotify URI
    if rd_is_pending:
        # RD is still downloading — don't mark as failed yet
        logger.info(f"  ⏳ RD pending, SpotiFLAC unavailable — will sweep later")
        return "rd_pending", rd_result

    error_parts = [f"RD: {rd_result.get('error','no results')}"]
    if spotify_uri:
        error_parts.append("SF: fallback failed")
    else:
        error_parts.append("No Spotify URI for fallback")
    error = " | ".join(error_parts)
    if not dry_run:
        update_status(queue_id, "failed", error=error[:500])
    return "failed"


# ──────────────────────────────────────────────────────────────
# RD Sweep — check back on pending torrents after harvest
# ──────────────────────────────────────────────────────────────

def _sweep_rd_pending(
    pending: Dict[str, Dict],
    stats: Dict[str, int],
    dry_run: bool = False,
    max_wait: int = 120,
    poll_interval: int = 15,
) -> None:
    """
    After the main harvest loop, wait for any RD torrents that were
    submitted but hadn't finished downloading yet.

    Args:
        pending: {torrent_id: {queue_id, artist, album, title}}
        stats: harvest stats dict (mutated in place)
        max_wait: total seconds to wait for stragglers
        poll_interval: seconds between status checks
    """
    import time
    from oracle.hunter import Hunter

    if dry_run:
        logger.info(f"  🧪 DRY RUN: would sweep {len(pending)} pending torrent(s)")
        return

    hunter = Hunter()
    remaining = dict(pending)
    waited = 0

    while remaining and waited < max_wait:
        time.sleep(poll_interval)
        waited += poll_interval
        logger.info(f"  ⏳ Sweep check ({waited}s / {max_wait}s) — {len(remaining)} pending")

        done_ids = []
        for tid, info in remaining.items():
            status = hunter.check_torrent(tid)
            rd_status = status.get("status")

            if rd_status == "downloaded":
                links = status.get("links", [])
                if links:
                    logger.info(f"  ✅ RD torrent ready: {info['title']} ({len(links)} link(s))")
                    paths = hunter.download_torrent_links(links)
                    if paths:
                        for p in paths:
                            _organize_rd_download(
                                Path(p), info["artist"], info.get("album")
                            )
                        update_status(info["queue_id"], "complete")
                        stats["complete"] = stats.get("complete", 0) + 1
                        done_ids.append(tid)
                    else:
                        logger.warning(f"  ⚠️  Downloaded but no files extracted for {info['title']}")
                else:
                    logger.warning(f"  ⚠️  RD says downloaded but no links for {info['title']}")

            elif rd_status in ("error", "magnet_error", "virus", "dead"):
                logger.warning(f"  ✗ RD torrent died: {info['title']} ({rd_status})")
                done_ids.append(tid)

            else:
                progress = status.get("progress", 0)
                if waited % 30 == 0:
                    logger.info(f"     {info['title']}: {progress}% ({rd_status})")

        for tid in done_ids:
            del remaining[tid]

    if remaining:
        logger.info(f"  ⏰ Sweep timeout — {len(remaining)} torrent(s) still downloading on RD")
        logger.info(f"     They'll keep downloading on RD. Run harvest again later to pick them up.")


# ──────────────────────────────────────────────────────────────
# Pre-harvest: collect previously submitted RD torrents
# ──────────────────────────────────────────────────────────────

def _collect_previous_rd_downloads(
    pending_targets: List[Tuple[int, str, str, str, str]],
    stats: Dict[str, int],
    processed_albums: set[str],
    dry_run: bool = False,
) -> set[int]:
    """Check RD for completed torrents from prior runs and download them.

    Matches RD torrent filenames against pending queue items by artist name.
    Returns set of queue_ids that were fulfilled.
    """
    from oracle.hunter import Hunter

    hunter = Hunter()
    torrents = hunter.list_rd_torrents(limit=100)

    if not torrents:
        return set()

    # Only care about completed torrents with links
    ready = [t for t in torrents if t.get("status") == "downloaded" and t.get("links")]
    if not ready:
        return set()

    logger.info(f"🔍 Found {len(ready)} completed RD torrent(s) from prior runs")

    # Deduplicate RD torrents by filename (earlier runs may have added the same torrent)
    seen_filenames: set[str] = set()
    unique_ready = []
    for t in ready:
        fn = (t.get("filename") or "").lower()
        if fn and fn not in seen_filenames:
            seen_filenames.add(fn)
            unique_ready.append(t)
    ready = unique_ready

    # Build a lookup: lowercase artist → list of (queue_id, artist, title, album)
    artist_lookup: Dict[str, List[tuple]] = {}
    for qid, art, title, album, uri in pending_targets:
        key = (art or "").lower().strip()
        artist_lookup.setdefault(key, []).append((qid, art, title, album))

    fulfilled: set[int] = set()

    for torrent in ready:
        filename = (torrent.get("filename") or "").lower()
        if not filename:
            continue

        # Try to match against any pending artist
        for artist_key, items in artist_lookup.items():
            if not artist_key or artist_key not in filename:
                continue

            # Skip if every pending item for this artist was already fulfilled
            unfulfilled = [(qid, a, t, alb) for qid, a, t, alb in items if qid not in fulfilled]
            if not unfulfilled:
                continue

            # This RD torrent contains music from a pending artist
            _, art, _, _ = unfulfilled[0]
            links = torrent.get("links", [])

            # Try to extract a real album name from the torrent filename
            # Patterns: "Artist - Album (year)" or "Artist - Album [flags]"
            rd_album = _parse_album_from_torrent(torrent.get("filename", ""), art)

            logger.info(
                f"  ✅ RD torrent matches [{art}]: {torrent.get('filename')} "
                f"({len(links)} link(s)) → album: {rd_album or '?'}"
            )

            if dry_run:
                logger.info(f"  🧪 DRY RUN: would download {len(links)} link(s)")
                continue

            # Download all links
            paths = hunter.download_torrent_links(links)
            if paths:
                use_album = rd_album or unfulfilled[0][3]  # fallback to queue album
                for p in paths:
                    _organize_rd_download(Path(p), art, use_album)

                # Mark unfulfilled pending tracks for this artist as complete
                album_key = f"{artist_key}|||{(use_album or '').lower()}"
                processed_albums.add(album_key)

                for qid, a, t, alb in unfulfilled:
                    update_status(qid, "complete")
                    fulfilled.add(qid)
                    stats["complete"] = stats.get("complete", 0) + 1
                    logger.info(f"    ⏭️  Fulfilled from RD: {a} — {t}")

            break  # Don't re-match this torrent

    return fulfilled


def _parse_album_from_torrent(filename: str, artist: str) -> str | None:
    """Try to extract an album name from an RD torrent filename.

    Common patterns:
        "Artist - Album (2023) [FLAC]"
        "Artist - Album [FLAC]"
        "(2023) Artist - Album [FLAC]"
    """
    # Strip leading year like "(2022) "
    cleaned = re.sub(r"^\(\d{4}\)\s*", "", filename).strip()

    # Try "Artist - Album" split
    parts = cleaned.split(" - ", 1)
    if len(parts) == 2:
        album_part = parts[1].strip()
        # Remove trailing year, quality tags, brackets
        album_part = re.sub(r"\s*[\(\[].*", "", album_part).strip()
        if album_part:
            return album_part

    return None


# ──────────────────────────────────────────────────────────────
# Harvest — process the acquisition queue
# ──────────────────────────────────────────────────────────────

def start_harvest(
    limit: int = 10,
    dry_run: bool = False,
    artist: str | None = None,
    whole_artist: bool = False,
    quality_preference: str = "FLAC",
) -> Dict[str, int]:
    """Process pending queue items through the tiered waterfall."""
    if whole_artist and not artist:
        logger.error("--whole-artist requires --artist \"Artist Name\".")
        return {}

    targets = fetch_pending_targets(limit=limit, artist=artist, whole_artist=whole_artist)

    if not targets:
        if artist:
            logger.info(f"No pending targets for artist: {artist}")
        else:
            logger.info("Queue empty. Run 'python spotify_import.py --queue' first.")
        return {}

    logger.info(f"🚀 Starting Harvest: {len(targets)} targets")
    logger.info(f"📁 Library: {LIBRARY_BASE}")
    logger.info(f"⚙️  Waterfall: Real-Debrid → SpotiFLAC\n")

    stats: Dict[str, int] = {"complete": 0, "failed": 0, "skipped": 0, "dry_run": 0}

    # Group by album for smarter RD batching —
    # if RD grabs a whole album, mark all tracks from that album as complete
    album_groups: Dict[str, List[tuple]] = {}
    for row in targets:
        qid, art, title, album, uri = row
        key = f"{(art or '').lower()}|||{(album or '').lower()}"
        album_groups.setdefault(key, []).append(row)

    processed_albums: set[str] = set()

    # ── PRE-SWEEP: grab any completed RD torrents from previous runs ──
    already_fulfilled = _collect_previous_rd_downloads(
        targets, stats, processed_albums, dry_run=dry_run,
    )

    # Pending RD torrents: {torrent_id: {queue_id, artist, album, title}}
    rd_pending: Dict[str, Dict] = {}

    for row in targets:
        qid, art, title, album, uri = row
        album_key = f"{(art or '').lower()}|||{(album or '').lower()}"

        # If this album was already grabbed via RD (album-level), skip individual tracks
        if album_key in processed_albums:
            logger.info(f"  ⏭️  Album already acquired: {art} — {title}")
            if not dry_run:
                update_status(qid, "complete")
            stats["complete"] += 1
            continue

        # Already fulfilled by the pre-sweep
        if qid in already_fulfilled:
            continue

        result = acquire_track(
            qid, art, title, album, uri,
            dry_run=dry_run, quality_preference=quality_preference,
        )

        # acquire_track returns a tuple when RD is pending
        if isinstance(result, tuple) and result[0] == "rd_pending":
            rd_info = result[1]
            tid = rd_info.get("torrent_id")
            if tid:
                rd_pending[tid] = {
                    "queue_id": qid, "artist": art,
                    "album": album, "title": title,
                }
                logger.info(f"  ⏳ Parked RD torrent {tid} — will sweep later")
            # Still fall through to SpotiFLAC inside acquire_track,
            # but track it for the sweep
            # Don't count as complete yet — SpotiFLAC may have handled it
            continue

        status = result
        stats[status] = stats.get(status, 0) + 1

        # If RD succeeded and this had album info, mark the album as processed
        # so sibling tracks from the same album get auto-completed
        if status == "complete" and album:
            processed_albums.add(album_key)

    # ── RD SWEEP: check back on pending torrents ──
    if rd_pending:
        logger.info(f"\n{'─'*50}")
        logger.info(f"🔄 Sweeping {len(rd_pending)} pending RD torrent(s)...")
        _sweep_rd_pending(rd_pending, stats, dry_run)

    logger.info(f"\n{'='*50}")
    logger.info(f"Harvest complete: {stats}")
    return stats


# ──────────────────────────────────────────────────────────────
# DISCOGRAPHY MODE — Spotify API → full artist catalog
# ──────────────────────────────────────────────────────────────

def _get_spotify_client(scopes: Optional[str] = None):
    """Authenticate and return a spotipy client."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    redirect_uri = "http://127.0.0.1:42069/callback"
    scope_str = scopes or "user-library-read"

    cache_path = Path(__file__).parent / ".spotify_cache"
    auth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=redirect_uri,
        scope=scope_str,
        cache_path=str(cache_path),
        open_browser=True,
    )
<<<<<<< HEAD
    return spotipy.Spotify(auth_manager=auth, requests_timeout=30)
=======
    return spotipy.Spotify(
        auth_manager=auth,
        requests_timeout=30,
        retries=0,
        status_retries=0,
        backoff_factor=0.0,
    )
>>>>>>> fc77b41 (Update workspace state and diagnostics)


def _resolve_artist(sp, artist_name: str) -> Optional[Dict]:
    """Find the best-matching artist on Spotify."""
<<<<<<< HEAD
    results = sp.search(q=f"artist:{artist_name}", type="artist", limit=5)
=======
    results = _spotify_call(sp.search, q=f"artist:{artist_name}", type="artist", limit=5)
    if not results:
        logger.warning(f"Spotify search unavailable/rate-limited for artist lookup: {artist_name}")
        return None
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    artists = results.get("artists", {}).get("items", [])
    if not artists:
        logger.error(f"Artist not found on Spotify: {artist_name}")
        return None

    wanted_norm = _normalize_artist_identity(artist_name)

    for a in artists:
        if _normalize_artist_identity(a["name"]) == wanted_norm:
            return a

    for a in artists:
        if a["name"].lower().strip() == artist_name.lower().strip():
            return a

    best = artists[0]
    logger.warning(
        f"  No exact artist identity match; using closest result: "
        f"{best['name']} (searched: {artist_name})"
    )
    return best

def _fetch_artist_albums(sp, artist_id: str) -> List[Dict]:
    """Fetch all album objects for an artist, including appears_on."""
    all_albums: List[Dict] = []
    # Primary catalog + compilations + appears_on (soundtracks, features, VA)
    for album_type in ["album,single,compilation", "appears_on"]:
        offset = 0
        while True:
<<<<<<< HEAD
            resp = sp.artist_albums(artist_id, album_type=album_type, limit=50, offset=offset)
=======
            resp = _spotify_call(
                sp.artist_albums,
                artist_id,
                album_type=album_type,
                limit=50,
                offset=offset,
            )
            if not resp:
                logger.warning("Spotify artist_albums unavailable/rate-limited; stopping album fetch early.")
                break
>>>>>>> fc77b41 (Update workspace state and diagnostics)
            items = resp.get("items", [])
            if not items:
                break
            all_albums.extend(items)
            offset += 50
            if not resp.get("next"):
                break
    return all_albums


def _search_sweep(sp, artist_name: str, artist_id: str, seen_uris: set[str]) -> List[Dict]:
    """
    Broad Spotify search sweep to catch remixes, features, and deep cuts
    that don't appear under the artist's own discography.

    Searches for:
      - "{artist} remix"        → other artists' remixes featuring them
      - "{artist} feat"         → features on other artists' tracks
      - "{artist} live"         → live recordings and bootlegs
      - "{artist} acoustic"     → acoustic versions
      - "{artist} cover"        → cover recordings
      - "{artist} version"      → alternate versions, radio edits
    """
    sweep_queries = [
        f'artist:"{artist_name}" remix',
        f'"{artist_name}" remix',
        f'"{artist_name}" feat',
        f'"{artist_name}" live',
        f'"{artist_name}" acoustic',
        f'"{artist_name}" version',
        f'"{artist_name}" remaster',
        f'"{artist_name}" demo',
    ]

    found: List[Dict] = []

    for query in sweep_queries:
        try:
            offset = 0
            while offset < 200:  # Cap at 200 results per query
<<<<<<< HEAD
                resp = sp.search(q=query, type="track", limit=50, offset=offset)
=======
                resp = _spotify_call(sp.search, q=query, type="track", limit=50, offset=offset)
                if not resp:
                    logger.warning("  ⚠️  Search sweep halted for query due Spotify rate-limit/offline.")
                    break
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                tracks = resp.get("tracks", {}).get("items", [])
                if not tracks:
                    break

                for t in tracks:
                    uri = t.get("uri", "")
                    if uri in seen_uris:
                        continue

                    # Match by Spotify artist ID to avoid name-collision contamination.
                    track_artist_ids = [a.get("id") for a in t.get("artists", []) if a.get("id")]
                    if artist_id not in track_artist_ids:
                        continue

                    seen_uris.add(uri)
                    album = t.get("album", {})
                    found.append({
                        "artist": artist_name,
                        "title": t["name"],
                        "album": album.get("name", ""),
                        "spotify_uri": uri,
                        "track_number": t.get("track_number", 0),
                        "disc_number": t.get("disc_number", 1),
                        "duration_ms": t.get("duration_ms", 0),
                        "source": "web_search",
                    })

                offset += 50
                if not resp.get("tracks", {}).get("next"):
                    break

        except Exception as exc:
            logger.warning(f"  ⚠️  Search sweep failed for [{query}]: {exc}")
            continue

    return found


def fetch_artist_discography(artist_name: str, sp: Optional[object] = None) -> List[Dict]:
    """
    Comprehensive artist discography fetch — three layers:

    1. Primary catalog: artist_albums (albums, singles, compilations)
    2. Appearances: artist_albums(appears_on) — soundtracks, VA comps, features
    3. Web search sweep: remixes, alternate versions, live cuts, features
       on other artists' tracks that Spotify doesn't link in the discography

    Requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET in .env.
    """
    try:
        import spotipy  # noqa: F401
    except ImportError:
        logger.error("spotipy not installed — pip install spotipy")
        return []

    if sp is None:
        sp = _get_spotify_client()
    artist_obj = _resolve_artist(sp, artist_name)
    if not artist_obj:
        return []

    artist_id = artist_obj["id"]
    artist_real_name = artist_obj["name"]
    logger.info(f"🎤 Artist: {artist_real_name} (Spotify ID: {artist_id})")

    # ── Layer 1+2: All albums (own catalog + appears_on) ──
    raw_albums = _fetch_artist_albums(sp, artist_id)
    logger.info(f"  📀 {len(raw_albums)} total releases (catalog + appears_on)")

    # Deduplicate albums by normalized name
    seen_albums: set[str] = set()
    unique_albums: List[Dict] = []
    for alb in raw_albums:
        norm = _normalize(alb["name"])
        if norm not in seen_albums:
            seen_albums.add(norm)
            unique_albums.append(alb)

    logger.info(f"  📀 {len(unique_albums)} unique albums after dedup")

    # Fetch tracks for each album
    all_tracks: List[Dict] = []
    seen_uris: set[str] = set()

    for alb in unique_albums:
        album_name = alb["name"]

<<<<<<< HEAD
        tracks_resp = sp.album_tracks(alb["id"], limit=50)
        items = tracks_resp.get("items", [])
        while tracks_resp.get("next"):
            tracks_resp = sp.next(tracks_resp)
=======
        tracks_resp = _spotify_call(sp.album_tracks, alb["id"], limit=50)
        if not tracks_resp:
            logger.warning(f"    ⚠️  Album tracks fetch skipped due Spotify rate-limit: {album_name}")
            continue
        items = tracks_resp.get("items", [])
        while tracks_resp.get("next"):
            tracks_resp = _spotify_call(sp.next, tracks_resp)
            if not tracks_resp:
                logger.warning(f"    ⚠️  Pagination halted due Spotify rate-limit: {album_name}")
                break
>>>>>>> fc77b41 (Update workspace state and diagnostics)
            items.extend(tracks_resp.get("items", []))

        album_count = 0
        for t in items:
            uri = t.get("uri", "")
            if uri in seen_uris:
                continue

            # Match by Spotify artist ID, not display name.
            track_artist_ids = [a.get("id") for a in t.get("artists", []) if a.get("id")]
            credited = artist_id in track_artist_ids

            if not credited:
                continue

            seen_uris.add(uri)
            all_tracks.append({
                "artist": artist_real_name,
                "title": t["name"],
                "album": album_name,
                "spotify_uri": uri,
                "track_number": t.get("track_number", 0),
                "disc_number": t.get("disc_number", 1),
                "duration_ms": t.get("duration_ms", 0),
                "source": "discography",
            })
            album_count += 1

        if album_count > 0:
            logger.info(f"    {album_name}: {album_count} tracks")

    logger.info(f"  🎵 {len(all_tracks)} tracks from artist catalog")

    # ── Layer 3: Web search sweep (remixes, features, deep cuts) ──
    logger.info("  🌐 Running web search sweep for remixes, features, and variants...")
    sweep_tracks = _search_sweep(sp, artist_real_name, artist_id, seen_uris)
    if sweep_tracks:
        all_tracks.extend(sweep_tracks)
        logger.info(f"  🌐 +{len(sweep_tracks)} additional tracks from search sweep")
    else:
        logger.info("  🌐 No additional tracks found in sweep")

    logger.info(f"  🎵 {len(all_tracks)} total tracks (catalog + appearances + sweep)")
    return all_tracks


<<<<<<< HEAD
=======
def _fallback_discography_from_history(artist_name: str, limit: int = 5000) -> List[Dict]:
    """Fallback discography source from local spotify_history when API is unavailable."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT artist, track, album, spotify_track_uri, COUNT(*) AS plays, MAX(played_at) AS last_played
            FROM spotify_history
            WHERE lower(artist) = lower(?)
              AND track IS NOT NULL
              AND trim(track) != ''
            GROUP BY artist, track, album, spotify_track_uri
            ORDER BY plays DESC, last_played DESC
            LIMIT ?
            """,
            (artist_name, int(limit)),
        )
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.warning(f"  ⚠️  spotify_history fallback failed: {exc}")
        rows = []
    finally:
        conn.close()

    tracks: List[Dict] = []
    seen: set[str] = set()
    for artist, title, album, uri, _plays, _last_played in rows:
        key = f"{_normalize(artist)}|||{_normalize(title)}|||{_normalize(album or '')}"
        if key in seen:
            continue
        seen.add(key)
        tracks.append(
            {
                "artist": artist or artist_name,
                "title": title,
                "album": album or "",
                "spotify_uri": uri or "",
                "track_number": 0,
                "disc_number": 1,
                "duration_ms": 0,
                "source": "spotify_history_fallback",
            }
        )
    if tracks:
        logger.info(f"  📚 Fallback from spotify_history: {len(tracks)} tracks")
    return tracks


>>>>>>> fc77b41 (Update workspace state and diagnostics)
def run_discography_mode(
    artist_name: str,
    dry_run: bool = False,
    skip_owned: bool = True,
    quality_preference: str = "FLAC",
    sp: Optional[object] = None,
) -> Dict[str, int]:
    """
    Full discography acquisition for an artist.

    1. Fetch complete discography via Spotify API
    2. Filter out already-owned and already-queued tracks
    3. Enqueue new tracks into acquisition_queue
    4. Run the tiered waterfall on all pending tracks for this artist
    """
    logger.info(f"{'='*60}")
    logger.info(f"  DISCOGRAPHY MODE: {artist_name}")
    logger.info(f"{'='*60}\n")

<<<<<<< HEAD
    disco_tracks = fetch_artist_discography(artist_name, sp=sp)
    if not disco_tracks:
=======
    try:
        disco_tracks = fetch_artist_discography(artist_name, sp=sp)
    except Exception as exc:
        logger.warning(f"  ⚠️  Spotify API discography fetch failed: {exc}")
        disco_tracks = []
    if not disco_tracks:
        logger.warning("  ⚠️  Spotify API discography unavailable; using local spotify_history fallback.")
        disco_tracks = _fallback_discography_from_history(artist_name)
    if not disco_tracks:
        logger.warning("  ⚠️  No discography tracks available from API or local fallback.")
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        return {}

    conn = get_connection()
    cur = conn.cursor()

    # Check what's already in queue (any status)
    cur.execute(
        "SELECT lower(title) FROM acquisition_queue WHERE lower(artist) = lower(?)",
        (artist_name,),
    )
    already_queued = {row[0] for row in cur.fetchall()}

    # Check local ownership
    new_tracks: List[Dict] = []
    owned_count = 0
    queued_count = 0

    for t in disco_tracks:
        norm_title = _normalize(t["title"])

        if norm_title in already_queued:
            queued_count += 1
            continue

        if skip_owned and _check_local_ownership(t["artist"], t["title"]):
            owned_count += 1
            continue

        new_tracks.append(t)

    logger.info(f"  ✅ Already owned locally:  {owned_count}")
    logger.info(f"  📋 Already in queue:       {queued_count}")
    logger.info(f"  🆕 New tracks to enqueue:  {len(new_tracks)}")

    if not new_tracks:
        logger.info("  Nothing new to acquire — discography is complete! 🎉")
        conn.close()
        return {"owned": owned_count, "queued": queued_count, "new": 0}

    # Enqueue the new tracks
    if not dry_run:
        for t in new_tracks:
            search_query = (
                f"{t['artist']} - {t['album']}"
                if t.get("album")
                else f"{t['artist']} - {t['title']}"
            )
            cur.execute(
                """INSERT INTO acquisition_queue
                   (artist, title, album, spotify_uri, priority_score, play_count, source, search_query)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    t["artist"], t["title"], t.get("album", ""),
                    t.get("spotify_uri", ""), 50.0, 0, "discography", search_query,
                ),
            )
        conn.commit()
        logger.info(f"  📥 Enqueued {len(new_tracks)} new tracks")
    else:
        logger.info(f"\n  🧪 DRY RUN — would enqueue {len(new_tracks)} tracks:")
        for t in new_tracks:
            logger.info(f"    • {t['artist']} — {t['title']} ({t.get('album','')})")

    conn.close()

    # Now harvest everything for this artist
    logger.info(f"\n{'='*60}")
    logger.info(f"  HARVESTING: {artist_name} (whole artist)")
    logger.info(f"{'='*60}\n")

    return start_harvest(
        limit=9999,
        dry_run=dry_run,
        artist=artist_name,
        whole_artist=True,
        quality_preference=quality_preference,
    )


# Top artists — discography helper
def get_top_artists(limit: int = 20, time_range: str = "medium_term") -> Tuple[List[str], Optional[object]]:
    """
    Get the user's top artists.

    Primary source: Spotify current_user_top_artists (needs user-top-read).
    Fallback: local spotify_history by play count.
    Returns (artist_names, spotify_client_or_none).
    """
    artists: List[str] = []
    sp_client: Optional[object] = None

    # Spotify API (preferred)
    try:
        sp_client = _get_spotify_client(scopes="user-top-read user-library-read")
<<<<<<< HEAD
        resp = sp_client.current_user_top_artists(limit=limit, time_range=time_range)
=======
        resp = _spotify_call(sp_client.current_user_top_artists, limit=limit, time_range=time_range)
        if not resp:
            raise RuntimeError("Spotify top artists unavailable/rate-limited")
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        items = resp.get("items", []) if resp else []
        artists = [a.get("name", "") for a in items if a.get("name")]
        if artists:
            logger.info(f"Top artists from Spotify ({time_range}): {len(artists)}")
            return artists, sp_client
        logger.warning("Spotify top artists API returned no artists — falling back to spotify_history")
    except Exception as exc:
        logger.warning(f"Spotify top artists failed: {exc} — falling back to spotify_history")
        sp_client = None

    # Fallback: local streaming history
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT artist, COUNT(*) AS plays "
            "FROM spotify_history "
            "GROUP BY artist "
            "ORDER BY plays DESC "
            "LIMIT ?",
            (limit,),
        )
        artists = [row[0] for row in cur.fetchall() if row[0]]
    except sqlite3.Error as exc:
        logger.error(f"Database error while computing top artists: {exc}")
        artists = []
    finally:
        conn.close()

    if artists:
        logger.info(f"Top artists from spotify_history: {len(artists)}")
    else:
        logger.error("No top artists found from Spotify API or local history")

    return artists, sp_client


def run_top_discographies(
    limit: int = 20,
    time_range: str = "medium_term",
    dry_run: bool = False,
    quality_preference: str = "FLAC",
) -> Dict[str, int]:
    """
    Fetch and acquire discographies for the user's top artists.
    """
    artists, sp_client = get_top_artists(limit=limit, time_range=time_range)
    if not artists:
        logger.error("No artists to process.")
        return {}

    results: Dict[str, int] = {
        "artists_total": len(artists),
        "artists_completed": 0,
        "artists_failed": 0,
    }

    for name in artists:
        logger.info("\n" + "=" * 60)
        logger.info(f"  TOP ARTIST DISCOGRAPHY: {name}")
        logger.info("=" * 60 + "\n")
        try:
            run_discography_mode(
                name,
                dry_run=dry_run,
                quality_preference=quality_preference,
                sp=sp_client,
            )
            results["artists_completed"] += 1
        except Exception as exc:
            logger.error(f"Failed to process {name}: {exc}")
            results["artists_failed"] += 1

    logger.info(f"Top discography run finished: {results}")
    return results


# ──────────────────────────────────────────────────────────────
# LIKED SONGS FOLDER LINKING
# ──────────────────────────────────────────────────────────────

def link_liked_songs(dry_run: bool = False) -> Dict[str, int]:
    """
    Create a 'Liked Songs' folder with symlinks to actual library files
    for every track in spotify_library where source='liked'.

    Cross-references spotify_library.artist/title against tracks.artist/title
    to find the local file path.
    """
    liked_dir = LIBRARY_BASE / "Liked Songs"

    conn = get_connection()
    cur = conn.cursor()

    # Check if spotify_library exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spotify_library'")
    if not cur.fetchone():
        logger.error("spotify_library table not found. Run 'python spotify_import.py --library' first.")
        conn.close()
        return {}

    # Get all liked songs
    cur.execute(
        "SELECT artist, title, album FROM spotify_library WHERE source = 'liked'"
    )
    liked = cur.fetchall()
    logger.info(f"💜 {len(liked)} liked songs in Spotify library")

    stats = {"linked": 0, "not_found": 0, "already_linked": 0}

    if not dry_run:
        liked_dir.mkdir(parents=True, exist_ok=True)

    for artist, title, album in liked:
        # Find local file
        norm_a = _normalize(artist)
        norm_t = _normalize(title)
        cur.execute(
            """SELECT file_path FROM tracks
               WHERE status = 'active'
                 AND LOWER(artist) LIKE ? AND LOWER(title) LIKE ?
               LIMIT 1""",
            (f"%{norm_a}%", f"%{norm_t}%"),
        )
        row = cur.fetchone()

        if not row:
            stats["not_found"] += 1
            continue

        source_path = Path(row[0])
        if not source_path.exists():
            stats["not_found"] += 1
            continue

        # Build symlink name: "Artist - Title.ext"
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", f"{artist} - {title}")
        link_path = liked_dir / f"{safe_name}{source_path.suffix}"

        if link_path.exists():
            stats["already_linked"] += 1
            continue

        if dry_run:
            logger.info(f"  🧪 LINK: {link_path.name} → {source_path}")
            stats["linked"] += 1
        else:
            try:
                link_path.symlink_to(source_path)
                stats["linked"] += 1
            except OSError:
                # Symlinks on Windows may need admin — fall back to hard link
                try:
                    os.link(str(source_path), str(link_path))
                    stats["linked"] += 1
                except OSError as exc:
                    logger.warning(f"  ⚠️  Cannot link {link_path.name}: {exc}")
                    stats["not_found"] += 1

    logger.info(f"\n💜 Liked Songs linking: {stats}")
    if stats["not_found"] > 0:
        logger.info(f"  ℹ️  {stats['not_found']} liked songs not in local library yet — acquire them first!")

    conn.close()
    return stats


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Lyra Acquire — Tiered Acquisition Engine (Real-Debrid → SpotiFLAC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python lyra_acquire.py --limit 10                           Top 10 pending (RD first)
  python lyra_acquire.py --artist "Brand New" --limit 5       5 Brand New tracks
  python lyra_acquire.py --artist "Brand New" --whole-artist  All pending Brand New
  python lyra_acquire.py --artist "Brand New" --discography   Full discography via Spotify API
  python lyra_acquire.py --top-discographies --top-n 20       Discographies for your top 20 artists
  python lyra_acquire.py --link-liked                         Symlink liked songs folder
  python lyra_acquire.py --dry-run --limit 20                 Preview without downloading

Acquisition Waterfall:
  Tier 1: Prowlarr → Real-Debrid (album-level FLAC torrents, cached = instant)
  Tier 2: SpotiFLAC (track-level FLAC via Tidal/Qobuz/Amazon, fallback)
        """,
    )

    parser.add_argument("--limit", type=int, default=10, help="Max pending targets (default: 10)")
    parser.add_argument("--artist", help="Target a specific artist")
    parser.add_argument("--whole-artist", action="store_true", help="All pending tracks for --artist (ignores --limit)")
    parser.add_argument("--discography", action="store_true", help="Full discography from Spotify API + acquire all gaps")
    parser.add_argument("--top-discographies", action="store_true", help="Discographies for your top Spotify artists")
    parser.add_argument("--top-n", type=int, default=20, help="How many top artists to process (default: 20)")
    parser.add_argument(
        "--time-range",
        choices=["short_term", "medium_term", "long_term"],
        default="medium_term",
        help="Spotify time range for top artists (default: medium_term)",
    )
    parser.add_argument("--link-liked", action="store_true", help="Create Liked Songs folder with symlinks")
    parser.add_argument("--dry-run", action="store_true", help="Preview without downloading")
    parser.add_argument(
        "--quality", default="FLAC",
        choices=["FLAC", "MP3-320", "MP3-V0"],
        help="Quality preference for Prowlarr (default: FLAC)",
    )

    args = parser.parse_args()
<<<<<<< HEAD
=======
    _acquire_run_lock()
    atexit.register(_release_run_lock)
>>>>>>> fc77b41 (Update workspace state and diagnostics)

    # ── Liked Songs linking ──
    if args.link_liked:
        link_liked_songs(dry_run=args.dry_run)
        return

    # ── Top artists discographies ──
    if args.top_discographies:
        run_top_discographies(
            limit=args.top_n,
            time_range=args.time_range,
            dry_run=args.dry_run,
            quality_preference=args.quality,
        )
        return

    # ── Discography mode ──
    if args.discography:
        if not args.artist:
            logger.error("--discography requires --artist \"Artist Name\"")
            return
        run_discography_mode(
            args.artist,
            dry_run=args.dry_run,
            quality_preference=args.quality,
        )
        return

    # ── Standard harvest ──
    start_harvest(
        limit=args.limit,
        dry_run=args.dry_run,
        artist=args.artist,
        whole_artist=args.whole_artist,
        quality_preference=args.quality,
    )


if __name__ == "__main__":
    main()
