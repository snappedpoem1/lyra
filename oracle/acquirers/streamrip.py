"""Streamrip acquisition backend.

Optional fallback tier that shells out to streamrip's CLI (`rip`).
This module is intentionally defensive: if streamrip is missing or the CLI
flags are incompatible with the installed version, it fails closed with a
clear error and lets the waterfall continue.
"""

from __future__ import annotations

import hashlib
import logging
import os
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
_WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


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


def _streamrip_config_path() -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / "streamrip" / "config.toml"


def _qobuz_password_for_streamrip(raw_password: str) -> str:
    """Convert plaintext password to streamrip's expected qobuz format.

    streamrip/qobuz config expects md5 hash when `use_auth_token=false`.
    """
    value = (raw_password or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"[a-fA-F0-9]{32}", value):
        return value.lower()
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _hydrate_streamrip_credentials_from_env() -> None:
    """Sync Lyra env credentials into streamrip config when missing."""
    cfg = _streamrip_config_path()
    if not cfg.exists():
        return

    username = (os.getenv("QOBUZ_USERNAME", "") or os.getenv("QOBUZ_EMAIL", "")).strip()
    password_raw = (os.getenv("QOBUZ_PASSWORD", "") or os.getenv("QOBUZ_PASS", "")).strip()
    password = _qobuz_password_for_streamrip(password_raw)
    if not username or not password:
        return

    try:
        import tomlkit

        data = tomlkit.parse(cfg.read_text(encoding="utf-8"))
        qobuz = data.get("qobuz")
        if qobuz is None:
            qobuz = tomlkit.table()
            data["qobuz"] = qobuz

        changed = False
        current_user = str(qobuz.get("email_or_userid", "")).strip()
        current_pass = str(qobuz.get("password_or_token", "")).strip()
        if not current_user:
            qobuz["email_or_userid"] = username
            changed = True
        if not current_pass:
            qobuz["password_or_token"] = password
            changed = True
        if "use_auth_token" not in qobuz:
            qobuz["use_auth_token"] = False
            changed = True

        if changed:
            cfg.write_text(tomlkit.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed to hydrate streamrip config from env: %s", exc)


def _has_configured_source() -> bool:
    _hydrate_streamrip_credentials_from_env()
    cfg = _streamrip_config_path()
    if not cfg.exists():
        return False
    try:
        import tomllib

        data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return False

    qobuz = data.get("qobuz", {}) if isinstance(data, dict) else {}
    deezer = data.get("deezer", {}) if isinstance(data, dict) else {}
    soundcloud = data.get("soundcloud", {}) if isinstance(data, dict) else {}

    qobuz_ok = bool(str(qobuz.get("email_or_userid", "")).strip()) and bool(
        str(qobuz.get("password_or_token", "")).strip()
    )
    deezer_ok = bool(str(deezer.get("arl", "")).strip())
    soundcloud_ok = bool(str(soundcloud.get("client_id", "")).strip()) and bool(str(soundcloud.get("app_version", "")).strip())
    return qobuz_ok or deezer_ok or soundcloud_ok


def is_available() -> bool:
    return _find_rip_executable() is not None and _has_configured_source()


def _find_audio_files(root: Path) -> List[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _AUDIO_EXTS]


def _build_query(artist: str, title: str, album: Optional[str] = None) -> str:
    parts = [artist.strip(), title.strip()]
    if album and album.strip():
        parts.append(album.strip())
    return " ".join(part for part in parts if part)


def _sanitize_filename_component(value: str) -> str:
    """Return a Windows-safe filename component."""
    cleaned = _WINDOWS_INVALID_CHARS.sub("", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Unknown"


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
    _hydrate_streamrip_credentials_from_env()
    rip = _find_rip_executable()
    if not rip:
        return {"success": False, "error": "streamrip CLI not available", "tier": 2, "source": "streamrip"}
    if not _has_configured_source():
        return {
            "success": False,
            "error": "streamrip has no configured source credentials",
            "tier": 2,
            "source": "streamrip",
        }

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
            for attempt in (1, 2):
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
                        safe_artist = _sanitize_filename_component(artist)
                        safe_title = _sanitize_filename_component(title)
                        safe_name = f"{safe_artist} - {safe_title}{src.suffix.lower()}"
                        dst = STAGING_FOLDER / safe_name
                        i = 1
                        while dst.exists():
                            dst = STAGING_FOLDER / f"{safe_artist} - {safe_title}_{i}{src.suffix.lower()}"
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
                    compact = _compact_error(err) if err else "streamrip no output"
                    transient = any(token in compact for token in ("AssertionError", "401", "total items"))
                    if transient and attempt < 2:
                        time.sleep(1.0 * attempt)
                        continue
                    errors.append(compact)
                    break
                except subprocess.TimeoutExpired:
                    if attempt < 2:
                        time.sleep(1.0 * attempt)
                        continue
                    errors.append(f"timeout after {timeout_seconds}s")
                    break
                except Exception as exc:
                    logger.debug("Streamrip attempt failed: %s", exc)
                    errors.append(str(exc)[:300])
                    break

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
