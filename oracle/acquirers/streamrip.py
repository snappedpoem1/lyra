"""Streamrip acquisition backend.

This module provides a real execution path for tier-2 acquisition by shelling
out to the `rip` CLI when available. It remains configuration-sensitive because
streamrip auth and provider setup are external concerns.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from oracle.config import STAGING_FOLDER, find_bundled_tool

logger = logging.getLogger(__name__)

_AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".aiff"}


def _rip_binary() -> Optional[str]:
    """Return the configured streamrip binary path, if present."""
    bundled = find_bundled_tool("rip.exe", "rip")
    if bundled:
        return bundled
    configured = os.getenv("LYRA_STREAMRIP_BINARY", "rip").strip() or "rip"
    return shutil.which(configured)


def _build_query(artist: str, title: str, album: Optional[str]) -> str:
    parts = [artist.strip(), title.strip()]
    if album and album.strip():
        parts.append(album.strip())
    return " ".join(part for part in parts if part)


def _build_command(binary: str, query: str, output_dir: Path) -> list[str]:
    """Build streamrip command from template or safe default.

    The default targets Qobuz track search using streamrip 2.x CLI syntax:
      rip -f <output_dir> search qobuz track <query> --first
    Override via LYRA_STREAMRIP_CMD_TEMPLATE with {binary}, {query}, {output_dir} slots.
    """
    template = os.getenv("LYRA_STREAMRIP_CMD_TEMPLATE", "").strip()
    if template:
        rendered = template.format(
            binary=binary,
            query=query,
            output_dir=str(output_dir),
        )
        return shlex.split(rendered, posix=False)

    # streamrip 2.x: `rip -f <dir> search <source> <media_type> <query> --first`
    source = os.getenv("LYRA_STREAMRIP_SOURCE", "qobuz").strip() or "qobuz"
    return [binary, "-f", str(output_dir), "search", source, "track", query, "--first"]


def _find_new_audio_file(output_dir: Path, started_at: float) -> Optional[Path]:
    """Return the newest audio file created/modified since started_at."""
    candidates = [
        p for p in output_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTS and p.stat().st_mtime >= started_at - 1.0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def is_available() -> bool:
    """Check whether streamrip CLI exists on PATH."""
    return _rip_binary() is not None


def download(
    artist: str,
    title: str,
    album: Optional[str] = None,
    output_dir: Optional[Path] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Attempt a streamrip acquisition for a track query.

    Args:
        artist: Artist name.
        title: Track title.
        album: Optional album hint.
        output_dir: Optional target directory for downloaded files.
        timeout_seconds: CLI timeout in seconds.

    Returns:
        Result dict compatible with waterfall tier expectations.
    """
    started = time.perf_counter()
    binary = _rip_binary()
    if not binary:
        return {
            "success": False,
            "error": "streamrip CLI not found (install streamrip and ensure `rip` is on PATH)",
            "tier": 2,
            "source": "streamrip",
            "elapsed": time.perf_counter() - started,
        }

    staging_root = Path(output_dir or STAGING_FOLDER).resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    query = _build_query(artist, title, album)
    command = _build_command(binary, query, staging_root)
    logger.info("[streamrip] running: %s", " ".join(command))

    command_started = time.time()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(30, int(timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"streamrip command timed out after {timeout_seconds}s",
            "tier": 2,
            "source": "streamrip",
            "elapsed": time.perf_counter() - started,
            "metadata": {"query": query},
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"streamrip command failed: {type(exc).__name__}: {exc}",
            "tier": 2,
            "source": "streamrip",
            "elapsed": time.perf_counter() - started,
            "metadata": {"query": query},
        }

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or f"exit code {proc.returncode}"
        return {
            "success": False,
            "error": f"streamrip search failed: {detail}",
            "tier": 2,
            "source": "streamrip",
            "elapsed": time.perf_counter() - started,
            "metadata": {"query": query, "command": command},
        }

    downloaded = _find_new_audio_file(staging_root, command_started)
    if not downloaded:
        return {
            "success": False,
            "error": "streamrip finished but no audio file was found in output directory",
            "tier": 2,
            "source": "streamrip",
            "elapsed": time.perf_counter() - started,
            "metadata": {"query": query, "output_dir": str(staging_root)},
        }

    return {
        "success": True,
        "path": str(downloaded),
        "artist": artist,
        "title": title,
        "tier": 2,
        "source": "streamrip",
        "elapsed": time.perf_counter() - started,
        "metadata": {
            "query": query,
            "output_dir": str(staging_root),
            "command": command,
        },
    }
