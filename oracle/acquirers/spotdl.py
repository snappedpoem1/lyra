"""spotDL acquisition backend (Tier 5) - WITH GUARD INTEGRATION.

Uses spotdl CLI to download from YouTube with Spotify metadata matching.
Now includes pre-flight and post-flight guard checks.

Requires: pip install spotdl
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = (PROJECT_ROOT / "downloads").resolve()
STAGING_DIR = (PROJECT_ROOT / "staging").resolve()

# Load .env so Spotify creds are available even when invoked directly
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

# Load Spotify creds from env (spotdl uses these for metadata lookups)
_SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
_SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def _find_spotdl() -> Optional[str]:
    """Find spotdl executable."""
    found = shutil.which("spotdl")
    if found:
        return found
    for candidate in [
        Path.home() / ".local" / "bin" / "spotdl",
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "Scripts" / "spotdl.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "spotdl.exe",
        PROJECT_ROOT / ".venv" / "bin" / "spotdl",
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def _sanitize_filename(name: str) -> str:
    """Remove problematic characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


class SpotDLAcquirer:
    """SpotDL-based acquisition (Tier 3) with guard integration."""

    def __init__(
        self,
        download_dir: Optional[Path] = None,
        staging_dir: Optional[Path] = None,
        use_guard: bool = True,
    ):
        self.download_dir = download_dir or DOWNLOAD_DIR
        self.staging_dir = staging_dir or STAGING_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.spotdl_path = _find_spotdl()
        self.use_guard = use_guard

    def is_available(self) -> bool:
        """Check if spotdl is available."""
        return self.spotdl_path is not None

    def _pre_flight_check(self, artist: str, title: str) -> Dict:
        """Run guard check BEFORE attempting download."""
        if not self.use_guard:
            return {"allowed": True, "artist": artist, "title": title}
        
        try:
            from oracle.acquirers.guard import guard_acquisition
            
            result = guard_acquisition(
                artist=artist,
                title=title,
                skip_validation=True,  # Skip MB check for speed, we'll verify after
                skip_duplicate_check=False,
            )
            
            if not result.allowed:
                return {
                    "allowed": False,
                    "reason": result.rejection_reason,
                    "category": result.rejection_category,
                }
            
            # Return cleaned metadata
            return {
                "allowed": True,
                "artist": result.artist,
                "title": result.title,
                "warnings": result.warnings,
            }
        except ImportError:
            logger.warning("Guard module not available, skipping pre-flight check")
            return {"allowed": True, "artist": artist, "title": title}

    def _post_flight_check(self, filepath: Path, expected_artist: str, expected_title: str) -> Dict:
        """Verify downloaded file matches expectations."""
        if not self.use_guard:
            return {"valid": True}
        
        try:
            import mutagen
            
            audio = mutagen.File(str(filepath), easy=True)
            if audio is None:
                return {"valid": False, "reason": "Could not read metadata from downloaded file"}
            
            file_artist = audio.get("artist", [""])[0] if audio.get("artist") else ""
            file_title = audio.get("title", [""])[0] if audio.get("title") else ""

            # Some malformed files parse but expose no artist/title tags.
            if not file_artist.strip() or not file_title.strip():
                return {
                    "valid": False,
                    "reason": "Downloaded file missing artist/title metadata tags",
                    "file_artist": file_artist,
                    "file_title": file_title,
                }
            
            # Check if downloaded file matches what we expected
            from difflib import SequenceMatcher
            
            artist_sim = SequenceMatcher(
                None, 
                expected_artist.lower(), 
                file_artist.lower()
            ).ratio()
            
            title_sim = SequenceMatcher(
                None,
                expected_title.lower(),
                file_title.lower()
            ).ratio()
            
            if artist_sim < 0.5 or title_sim < 0.5:
                return {
                    "valid": False,
                    "reason": f"Mismatch: expected '{expected_artist} - {expected_title}', "
                              f"got '{file_artist} - {file_title}'",
                    "file_artist": file_artist,
                    "file_title": file_title,
                }
            
            # Also run the junk check on actual metadata
            from oracle.acquirers.guard import guard_acquisition
            result = guard_acquisition(
                file_artist or expected_artist,
                file_title or expected_title,
                skip_validation=True,
                skip_duplicate_check=True,
            )
            
            if not result.allowed:
                return {
                    "valid": False,
                    "reason": f"Downloaded file is junk: {result.rejection_reason}",
                }
            
            return {"valid": True, "artist": file_artist, "title": file_title}
            
        except Exception as e:
            logger.warning(f"Post-flight check failed: {e}")
            return {"valid": False, "reason": f"Post-flight validation error: {e}"}

    def _ytdlp_fallback(self, artist: str, title: str) -> Dict:
        """Fall back to yt-dlp YouTube search when spotdl/Spotify is unavailable."""
        logger.info(f"[T3 yt-dlp fallback] Searching: {artist} - {title}")
        try:
            from oracle.acquirers.ytdlp import download_search
            result = download_search(artist, title)
            if result.get("success"):
                result["source"] = "ytdlp_fallback"
            return result
        except Exception as exc:
            logger.exception("[T3 yt-dlp fallback] Error")
            return {"success": False, "error": f"yt-dlp fallback failed: {exc}", "tier": 3}

    def download(self, artist: str, title: str, spotify_uri: Optional[str] = None) -> Dict:
        """Download track using spotdl with guard checks.

        Uses an isolated temp directory per call so parallel workers never
        race on the same output folder.

        Args:
            artist: Artist name
            title: Track title
            spotify_uri: Optional Spotify URI for exact match

        Returns:
            Result dict with success, path, error keys
        """
        import tempfile
        import threading

        if not self.spotdl_path:
            return {"success": False, "error": "spotdl not installed", "tier": 3}

        # PRE-FLIGHT CHECK
        preflight = self._pre_flight_check(artist, title)
        if not preflight.get("allowed"):
            logger.warning(f"[T3 SpotDL] Pre-flight rejected: {preflight.get('reason')}")
            return {
                "success": False,
                "error": f"Rejected: {preflight.get('reason')}",
                "rejection_category": preflight.get("category"),
                "tier": 3,
            }

        clean_artist = preflight.get("artist", artist)
        clean_title = preflight.get("title", title)
        query = spotify_uri if spotify_uri else f"{clean_artist} - {clean_title}"

        logger.info(f"[T3 SpotDL] Acquiring: {query}")

        # Isolated temp dir per download — safe for parallel workers
        try:
            with tempfile.TemporaryDirectory(
                prefix="spotdl_", dir=self.download_dir.parent
            ) as tmp_dir:
                tmp_path = Path(tmp_dir)

                cmd: List[str] = [
                    self.spotdl_path,
                    "download",
                    query,
                    "--output", str(tmp_path),
                    "--format", "mp3",
                    "--bitrate", "320k",
                    "--threads", "1",
                ]
                if _SPOTIFY_CLIENT_ID and _SPOTIFY_CLIENT_SECRET:
                    cmd += [
                        "--client-id", _SPOTIFY_CLIENT_ID,
                        "--client-secret", _SPOTIFY_CLIENT_SECRET,
                    ]

                output_lines: List[str] = []
                rate_limited = threading.Event()

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(tmp_path),
                )

                def _reader() -> None:
                    try:
                        assert proc.stdout is not None
                        for line in proc.stdout:
                            output_lines.append(line)
                            if "rate/request limit" in line or "rate limit" in line.lower():
                                rate_limited.set()
                                proc.kill()
                                break
                    except Exception:
                        pass

                reader_thread = threading.Thread(target=_reader, daemon=True)
                reader_thread.start()

                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()

                reader_thread.join(timeout=5)
                combined_output = "".join(output_lines)
                returncode = proc.poll() or 0

                if rate_limited.is_set():
                    logger.warning("[T3 SpotDL] Spotify rate-limited — falling back to yt-dlp")
                    return self._ytdlp_fallback(clean_artist, clean_title)

                if returncode != 0:
                    logger.warning(f"[T3 SpotDL] Failed (rc={returncode}): {combined_output[-200:]}")
                    return self._ytdlp_fallback(clean_artist, clean_title)

                # No race condition — tmp_path is exclusive to this download
                candidates = list(tmp_path.glob("*.mp3")) or list(tmp_path.glob("*.*"))
                if not candidates:
                    return {"success": False, "error": "No file downloaded", "tier": 3}

                downloaded = max(candidates, key=lambda p: p.stat().st_mtime)

                # POST-FLIGHT CHECK
                postflight = self._post_flight_check(downloaded, clean_artist, clean_title)
                if not postflight.get("valid"):
                    try:
                        downloaded.unlink()
                    except OSError:
                        pass
                    logger.warning(f"[T3 SpotDL] Post-flight rejected: {postflight.get('reason')}")
                    return {
                        "success": False,
                        "error": f"Downloaded file rejected: {postflight.get('reason')}",
                        "tier": 3,
                    }

                # Move to staging with clean filename
                clean_filename = _sanitize_filename(
                    f"{clean_artist} - {clean_title}{downloaded.suffix}"
                )
                target = self.staging_dir / clean_filename
                if target.exists():
                    target = self.staging_dir / (
                        f"{Path(clean_filename).stem}_{int(time.time())}{downloaded.suffix}"
                    )

                final_path = shutil.move(str(downloaded), str(target))
                logger.info(f"[T3 SpotDL] Success: {final_path}")
                return {
                    "success": True,
                    "path": str(final_path),
                    "tier": 3,
                    "source": "spotdl",
                    "artist": postflight.get("artist", clean_artist),
                    "title": postflight.get("title", clean_title),
                }

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning(f"[T3 SpotDL] Process error ({exc}) — falling back to yt-dlp search")
            return self._ytdlp_fallback(clean_artist, clean_title)
        except Exception as exc:
            logger.exception("[T3 SpotDL] Error")
            return {"success": False, "error": str(exc), "tier": 3}


_acquirer: Optional[SpotDLAcquirer] = None


def get_acquirer() -> SpotDLAcquirer:
    global _acquirer
    if _acquirer is None:
        _acquirer = SpotDLAcquirer()
    return _acquirer


def download(artist: str, title: str, spotify_uri: Optional[str] = None) -> Dict:
    """Convenience function."""
    return get_acquirer().download(artist, title, spotify_uri)


def is_available() -> bool:
    """Check if spotdl backend is available."""
    return get_acquirer().is_available()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 3:
        print("Usage: python -m oracle.acquirers.spotdl <artist> <title>")
        sys.exit(1)

    result = download(sys.argv[1], sys.argv[2])
    print(result)
