"""yt-dlp acquisition backend.

Supports both URL-based and search-based downloads.
Used as T3 fallback when spotdl's Spotify API is rate-limited.
"""

from __future__ import annotations

import logging
import os
import random
import re
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
import yt_dlp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

logger = logging.getLogger(__name__)


def _sleep_between_requests() -> None:
    sleep_min = int(os.getenv("SLEEP_MIN", "5"))
    sleep_max = int(os.getenv("SLEEP_MAX", "15"))
    time.sleep(random.uniform(sleep_min, sleep_max))


def _find_latest_file(folder: Path, suffix: str = ".mp3") -> Optional[Path]:
    candidates = [p for p in folder.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        candidates = [p for p in folder.glob("*.*") if p.is_file() and p.suffix.lower()
                      in (".mp3", ".m4a", ".flac", ".opus", ".webm")]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


class YTDLPAcquirer:
    """yt-dlp based acquirer supporting both URL and search queries."""

    def __init__(self, download_dir: str = "downloads", staging_dir: str = "staging"):
        self.download_dir = (PROJECT_ROOT / download_dir).resolve()
        self.staging_dir = (PROJECT_ROOT / staging_dir).resolve()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _options(self, outtmpl: Optional[str] = None) -> dict:
        return {
            "format": "bestaudio/best",
            "outtmpl": outtmpl or str(self.download_dir / "%(uploader)s - %(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 2,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": os.getenv("PREFERRED_CODEC", "mp3"),
                    "preferredquality": os.getenv("PREFERRED_QUALITY", "320"),
                }
            ],
        }

    def _move_to_staging(self, file_path: Path, clean_name: Optional[str] = None) -> Path:
        name = clean_name or file_path.name
        target = self.staging_dir / name
        if target.exists():
            target = self.staging_dir / f"{Path(name).stem}_{int(time.time())}{Path(name).suffix}"
        return Path(shutil.move(str(file_path), str(target)))

    def download(self, url: str) -> Optional[Path]:
        """Download from a direct URL. Returns staged path or None."""
        for attempt in range(1, 4):
            try:
                with yt_dlp.YoutubeDL(self._options()) as ydl:
                    ydl.download([url])
                latest = _find_latest_file(self.download_dir)
                if not latest:
                    return None
                return self._move_to_staging(latest)
            except Exception as exc:
                logger.warning(f"[yt-dlp] attempt {attempt} failed: {exc}")
                if attempt == 3:
                    return None
                _sleep_between_requests()
        return None

    def download_search(self, artist: str, title: str) -> Dict:
        """Search YouTube and download best match.

        Uses an isolated temp directory per call to prevent parallel-worker
        file collisions.  Verifies the downloaded video title matches the
        expected artist + title before accepting the result.

        Returns dict with success, path, tier, source, artist, title, error keys.
        """
        import tempfile
        from difflib import SequenceMatcher

        query = f"ytsearch1:{artist} {title}"
        clean_artist = _sanitize(artist)
        clean_title = _sanitize(title)
        target = f"{artist} {title}".lower()

        logger.info(f"[yt-dlp search] Searching: {artist} - {title}")

        try:
            with tempfile.TemporaryDirectory(
                prefix="ytdlp_", dir=self.download_dir.parent
            ) as tmp_dir:
                tmp_path = Path(tmp_dir)
                outtmpl = str(tmp_path / "%(title)s.%(ext)s")

                # Capture info to verify title similarity
                downloaded_title: Optional[str] = None

                class _InfoHook:
                    def __init__(self) -> None:
                        self.title: Optional[str] = None

                    def __call__(self, d: dict) -> None:
                        if d.get("status") == "finished" and not self.title:
                            self.title = d.get("info_dict", {}).get("title", "")

                hook = _InfoHook()
                opts = self._options(outtmpl=outtmpl)
                opts["progress_hooks"] = [hook]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([query])

                downloaded_title = hook.title or ""

                latest = _find_latest_file(tmp_path)
                if not latest:
                    return {"success": False, "error": "No file downloaded after search", "tier": 3}

                # Verify the video title is close enough to what we wanted
                video_title = downloaded_title or latest.stem
                similarity = SequenceMatcher(
                    None, target, video_title.lower()
                ).ratio()

                if similarity < 0.25:
                    logger.warning(
                        f"[yt-dlp search] Title mismatch (sim={similarity:.2f}): "
                        f"wanted '{artist} - {title}', got '{video_title}'"
                    )
                    return {
                        "success": False,
                        "error": f"YouTube result mismatch: got '{video_title}'",
                        "tier": 3,
                    }

                # Move to staging with clean filename
                clean_name = f"{clean_artist} - {clean_title}{latest.suffix}"
                staged = self._move_to_staging(latest, clean_name=clean_name)
                logger.info(f"[yt-dlp search] Success: {staged}")

            return {
                "success": True,
                "path": str(staged),
                "tier": 3,
                "source": "ytdlp",
                "artist": artist,
                "title": title,
            }

        except yt_dlp.utils.DownloadError as exc:
            return {"success": False, "error": str(exc)[:200], "tier": 3}
        except Exception as exc:
            logger.exception("[yt-dlp search] Error")
            return {"success": False, "error": str(exc)[:200], "tier": 3}


# Module-level singleton
_acquirer: Optional[YTDLPAcquirer] = None


def get_acquirer() -> YTDLPAcquirer:
    global _acquirer
    if _acquirer is None:
        _acquirer = YTDLPAcquirer()
    return _acquirer


def download_search(artist: str, title: str) -> Dict:
    """Convenience function for search-based download."""
    return get_acquirer().download_search(artist, title)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) == 3:
        result = download_search(sys.argv[1], sys.argv[2])
        print(result)
    elif len(sys.argv) == 2:
        result = get_acquirer().download(sys.argv[1])
        print(result)
    else:
        print("Usage: python -m oracle.acquirers.ytdlp <url>")
        print("       python -m oracle.acquirers.ytdlp <artist> <title>")
        sys.exit(1)
