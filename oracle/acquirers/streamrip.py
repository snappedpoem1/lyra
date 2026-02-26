"""Streamrip acquisition backend.

Optional fallback tier that shells out to streamrip's CLI (`rip`).
This module is intentionally defensive: if streamrip is missing or the CLI
flags are incompatible with the installed version, it fails closed with a
clear error and lets the waterfall continue.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

from oracle.config import STAGING_FOLDER

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _find_rip_executable() -> Optional[str]:
    """Locate streamrip CLI executable."""
    candidates = [
        "rip",
        "streamrip",
        str(PROJECT_ROOT / ".venv" / "Scripts" / "rip.exe"),
        str(PROJECT_ROOT / ".venv" / "Scripts" / "streamrip.exe"),
        str(PROJECT_ROOT / ".venv" / "bin" / "rip"),
        str(PROJECT_ROOT / ".venv" / "bin" / "streamrip"),
        str(Path.home() / ".local" / "bin" / "rip"),
        str(Path.home() / "AppData" / "Roaming" / "Python" / "Python312" / "Scripts" / "rip.exe"),
        str(Path.home() / "AppData" / "Roaming" / "Python" / "Python313" / "Scripts" / "rip.exe"),
        str(Path.home() / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts" / "rip.exe"),
    ]
    for candidate in candidates:
        found = shutil.which(candidate) if Path(candidate).name == candidate else None
        if found:
            return found
        if Path(candidate).exists():
            return str(Path(candidate))
    return None


def is_available() -> bool:
    return _find_rip_executable() is not None


def _find_audio_files(root: Path) -> List[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _AUDIO_EXTS]


def _build_query(artist: str, title: str, album: Optional[str] = None) -> str:
    parts = [artist.strip(), title.strip()]
    if album and album.strip():
        parts.append(album.strip())
    return " ".join(part for part in parts if part)


def _compact_error(text: str) -> str:
    cleaned = _ANSI_RE.sub("", text or "")
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines:
        return "unknown streamrip error"
    for ln in reversed(lines):
        if ln.startswith("Exception:"):
            return ln
        if "Error:" in ln:
            return ln
    return lines[-1][:300]


def download(artist: str, title: str, album: Optional[str] = None, timeout_seconds: int = 240) -> Dict:
    """Attempt acquisition via streamrip CLI.

    Returns a dict compatible with waterfall acquisition adapters.
    """
    start = time.perf_counter()
    rip = _find_rip_executable()
    if not rip:
        return {"success": False, "error": "streamrip CLI not available", "tier": 2, "source": "streamrip"}

    STAGING_FOLDER.mkdir(parents=True, exist_ok=True)
    query = _build_query(artist, title, album)
    if not query:
        return {"success": False, "error": "empty query", "tier": 2, "source": "streamrip"}

    # streamrip 2.x CLI shape:
    #   rip [global-opts] search SOURCE MEDIA_TYPE QUERY --first
    # Try multiple sources in order; we consider success only if an audio file appears.
    sources = ["qobuz", "deezer", "soundcloud"]
    commands = [
        [
            rip,
            "--folder",
            ".",
            "--no-progress",
            "search",
            src,
            "track",
            query,
            "--first",
        ]
        for src in sources
    ]

    errors: List[str] = []
    with tempfile.TemporaryDirectory(prefix="streamrip_", dir=str(STAGING_FOLDER.parent)) as tmp:
        tmp_path = Path(tmp)
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(tmp_path),
                    capture_output=True,
                    text=True,
                    timeout=int(timeout_seconds),
                    check=False,
                )
                files = _find_audio_files(tmp_path)
                if files:
                    src = max(files, key=lambda p: p.stat().st_mtime)
                    safe_name = f"{artist} - {title}{src.suffix.lower()}"
                    dst = STAGING_FOLDER / safe_name
                    i = 1
                    while dst.exists():
                        dst = STAGING_FOLDER / f"{artist} - {title}_{i}{src.suffix.lower()}"
                        i += 1
                    shutil.move(str(src), str(dst))
                    return {
                        "success": True,
                        "path": str(dst),
                        "artist": artist,
                        "title": title,
                        "tier": 2,
                        "source": "streamrip",
                        "elapsed": time.perf_counter() - start,
                    }
                err = (proc.stderr or proc.stdout or "").strip()
                if err:
                    errors.append(_compact_error(err))
            except subprocess.TimeoutExpired:
                errors.append(f"timeout after {timeout_seconds}s")
            except Exception as exc:
                logger.debug("Streamrip attempt failed: %s", exc)
                errors.append(str(exc)[:300])

    error = "streamrip did not produce an audio file"
    if errors:
        error = f"{error} ({errors[-1]})"
    return {
        "success": False,
        "error": error,
        "tier": 2,
        "source": "streamrip",
        "elapsed": time.perf_counter() - start,
    }
