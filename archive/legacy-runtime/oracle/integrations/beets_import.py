"""Beets integration -- auto-tag and organize files via beets import.

Wraps ``beet import`` as a subprocess with BEETSDIR pointing to the
project-local config at ``.beets/config.yaml``.  The acquisition guard
runs BEFORE beets sees any files so junk is quarantined first.

Typical usage::

    from oracle.integrations.beets_import import beets_import_and_ingest
    result = beets_import_and_ingest(Path("staging"))
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BEETSDIR = Path(__file__).resolve().parents[2] / ".beets"
AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_audio_files(source_dir: Path) -> List[Path]:
    """Recursively find all audio files in *source_dir*."""
    return sorted(
        p for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def _quarantine_file(filepath: Path, reason: str) -> None:
    """Move a rejected file to the quarantine directory."""
    from oracle.config import QUARANTINE_PATH

    q_dir = Path(QUARANTINE_PATH) / "Junk"
    q_dir.mkdir(parents=True, exist_ok=True)
    dest = q_dir / filepath.name
    if dest.exists():
        dest = q_dir / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
    shutil.move(str(filepath), str(dest))
    logger.info("[BEETS] Quarantined: %s -- %s", filepath.name, reason)


def _find_beet_executable() -> list:
    """Locate the ``beet`` CLI and return a command list for subprocess."""
    import sys
    import site

    # Prefer the current interpreter's environment (works even if VIRTUAL_ENV
    # is not set, e.g. when invoking ".venv\\Scripts\\python.exe -m ...").
    exe_path = Path(sys.executable)
    exe_dir = exe_path.parent
    candidates = [
        exe_dir / "beet.exe",
        exe_dir / "beet",
        exe_dir.parent / "Scripts" / "beet.exe",
        exe_dir.parent / "bin" / "beet",
    ]
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]

    # Check venv first
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv:
        venv_beet = Path(venv) / "Scripts" / "beet.exe"
        if venv_beet.exists():
            return [str(venv_beet)]
        venv_beet_unix = Path(venv) / "bin" / "beet"
        if venv_beet_unix.exists():
            return [str(venv_beet_unix)]

    # Fall back to PATH
    which = shutil.which("beet")
    if which:
        return [which]

    # Check user site-packages Scripts (pip install --user on Windows)
    try:
        user_scripts = Path(site.getusersitepackages()).parent / "Scripts"
        user_beet = user_scripts / "beet.exe"
        if user_beet.exists():
            return [str(user_beet)]
    except Exception:
        pass

    # Check known Python version user-script dirs (beets may be on a different Python)
    import os as _os
    appdata = Path(_os.environ.get("APPDATA", ""))
    for ver in ["Python314", "Python313", "Python312", "Python311"]:
        candidate = appdata / "Python" / ver / "Scripts" / "beet.exe"
        if candidate.exists():
            return [str(candidate)]

    # Last resort: python -m beets
    return [sys.executable, "-m", "beets"]


# ---------------------------------------------------------------------------
# Core import
# ---------------------------------------------------------------------------

def beets_import(
    source_dir: Path,
    *,
    quiet: bool = True,
    move: bool = True,
    singleton: bool = False,
    dry_run: bool = False,
    no_autotag: bool = False,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    """Import audio files from *source_dir* via beets.

    1. Find all audio files in *source_dir*.
    2. Run the acquisition guard on each -- quarantine rejects.
    3. Call ``beet import`` subprocess on the remaining files.

    Args:
        source_dir: Directory containing files to import.
        quiet: Auto-accept best MusicBrainz match (no prompts).
        move: Move files to library (True) or copy them (False).
        singleton: Import as non-album singletons.
        dry_run: Preview only -- beets won't move files.
        no_autotag: Skip MusicBrainz lookup; import with existing tags.
        timeout_seconds: Subprocess timeout.

    Returns:
        ``{audio_found, quarantined, imported, errors, beets_stdout, beets_stderr}``
    """
    source = Path(source_dir).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source directory not found: {source}")

    audio_files = _find_audio_files(source)
    stats: Dict[str, Any] = {
        "audio_found": len(audio_files),
        "quarantined": 0,
        "imported": 0,
        "errors": 0,
    }

    if not audio_files:
        logger.info("[BEETS] No audio files found in %s", source)
        return stats

    # --- Phase 1: Guard check ------------------------------------------------
    from oracle.acquirers.guard import guard_file

    passed: List[Path] = []
    for fp in audio_files:
        result = guard_file(fp)
        if not result.allowed:
            reason = result.rejection_reason or "guard rejected"
            _quarantine_file(fp, reason)
            stats["quarantined"] += 1
        else:
            passed.append(fp)

    if not passed:
        logger.info("[BEETS] All files quarantined. Nothing to import.")
        return stats

    # --- Phase 2: Beets import -----------------------------------------------
    beet_cmd = _find_beet_executable()
    cmd = beet_cmd + ["import"]
    if quiet:
        cmd.append("--quiet")
    if move:
        cmd.append("--move")
    else:
        cmd.append("--copy")
    if singleton:
        cmd.append("--singletons")
    if no_autotag:
        cmd.append("--noautotag")
    cmd.append(str(source))

    env = os.environ.copy()
    env["BEETSDIR"] = str(BEETSDIR)

    logger.info("[BEETS] Running: %s", " ".join(cmd))
    logger.info("[BEETS] BEETSDIR=%s", BEETSDIR)

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
        )
        stats["beets_stdout"] = proc.stdout
        stats["beets_stderr"] = proc.stderr

        if proc.returncode == 0:
            # Count how many files actually left the source (moved/imported)
            remaining = _find_audio_files(source)
            actually_imported = len(passed) - len(remaining)
            stats["imported"] = max(actually_imported, 0)
            skipped = proc.stdout.count("Skipping")
            if skipped:
                logger.warning("[BEETS] %d item(s) skipped by beets", skipped)
                stats["skipped"] = skipped
            logger.info(
                "[BEETS] Import completed: %d imported, %d skipped",
                stats["imported"], skipped,
            )
        else:
            logger.error(
                "[BEETS] Import failed (exit %d): %s",
                proc.returncode,
                proc.stderr[:500],
            )
            stats["errors"] = len(passed)

    except subprocess.TimeoutExpired:
        logger.error("[BEETS] Import timed out after %ds", timeout_seconds)
        stats["errors"] = len(passed)
    except FileNotFoundError:
        logger.error("[BEETS] beet executable not found")
        stats["errors"] = len(passed)

    return stats


# ---------------------------------------------------------------------------
# Auto-enrich helpers
# ---------------------------------------------------------------------------

def _enrich_recent_tracks(max_age_seconds: float = 300.0) -> int:
    """Enrich tracks added in the last *max_age_seconds* with Last.fm + Genius.

    Returns the number of tracks enriched.
    """
    try:
        from oracle.db.schema import get_connection
        from oracle.enrichers.unified import enrich_track

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cutoff = time.time() - max_age_seconds
        cursor.execute(
            "SELECT track_id FROM tracks WHERE added_at >= ? AND status = 'active'",
            (cutoff,),
        )
        track_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not track_ids:
            return 0

        enriched = 0
        for tid in track_ids:
            try:
                enrich_track(tid, providers=["lastfm", "genius"])
                enriched += 1
            except Exception as exc:
                logger.debug("[BEETS] Enrich failed for %s: %s", tid, exc)

        logger.info("[BEETS] Auto-enriched %d/%d tracks (lastfm + genius)", enriched, len(track_ids))
        return enriched
    except Exception as exc:
        logger.error("[BEETS] Auto-enrich failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Full pipeline: beets import -> scan -> index -> score
# ---------------------------------------------------------------------------

def beets_import_and_ingest(
    source_dir: Path,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Import via beets, then scan + index the library.

    Replaces the old ``ingest_watcher._move_to_library()`` + scan + index
    pipeline with beets-driven organization.
    """
    result = beets_import(source_dir, **kwargs)

    if result.get("imported", 0) > 0:
        from oracle.config import LIBRARY_BASE

        logger.info("[BEETS] Running post-import scan + index ...")

        try:
            from oracle.scanner import scan_library
            scan_result = scan_library(str(LIBRARY_BASE))
            result["scan"] = scan_result
            logger.info("[BEETS] Scan: %s", scan_result)
        except Exception as exc:
            logger.error("[BEETS] Scan failed: %s", exc)
            result["scan_error"] = str(exc)

        try:
            from oracle.indexer import index_library
            index_result = index_library()
            result["index"] = index_result
            logger.info("[BEETS] Index: %s", index_result)
        except Exception as exc:
            logger.error("[BEETS] Index failed: %s", exc)
            result["index_error"] = str(exc)

        # --- Phase 4: Auto-enrich newly ingested tracks -----------------------
        result["enriched"] = _enrich_recent_tracks()

    return result
