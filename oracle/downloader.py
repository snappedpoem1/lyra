"""
oracle.downloader — Music Acquisition Engine

Downloads audio from SoundCloud, YouTube, Bandcamp, etc. using yt-dlp.
Applies rate limiting, embeds metadata, handles batch operations.
"""

import os
import sys
import time
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from mutagen.mp4 import MP4
    from mutagen.easymp4 import EasyMP4
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

import requests as http_requests

logger = logging.getLogger("oracle.downloader")


def check_prowlarr(config) -> bool:
    """Check if Prowlarr indexer is online."""
    if not config.has_prowlarr:
        return False
    try:
        r = http_requests.get(
            f"{config.prowlarr_url}/api/v1/system/status",
            params={"apikey": config.prowlarr_api_key},
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


def search_prowlarr(config, query: str, limit: int = 10) -> list:
    """Search Prowlarr indexers for music releases."""
    if not config.has_prowlarr:
        return []
    try:
        r = http_requests.get(
            f"{config.prowlarr_url}/api/v1/search",
            params={
                "query": query,
                "type": "search",
                "limit": limit,
                "apikey": config.prowlarr_api_key,
            },
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


class DownloadResult:
    """Container for a single download result."""
    def __init__(self, success: bool, artist: str = "", title: str = "",
                 filepath: str = "", url: str = "", error: str = ""):
        self.success = success
        self.artist = artist
        self.title = title
        self.filepath = filepath
        self.url = url
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def __repr__(self):
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.artist} — {self.title}"


class Downloader:
    """yt-dlp based download engine with archival-grade settings."""

    def __init__(self, config, db_path: Path):
        if not yt_dlp:
            raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

        self.config = config
        self.db_path = db_path
        self.download_dir = config.download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._progress_callback: Optional[Callable] = None

    def _init_db(self):
        """Track what we've downloaded to avoid duplicates."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    artist TEXT,
                    title TEXT,
                    filepath TEXT,
                    codec TEXT,
                    quality TEXT,
                    filesize INTEGER,
                    duration REAL,
                    source_platform TEXT,
                    downloaded_at TEXT,
                    status TEXT DEFAULT 'ok'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS download_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    error TEXT,
                    attempted_at TEXT
                )
            """)

    def set_progress_callback(self, callback: Callable):
        """Set a callback for progress updates: callback(status_dict)."""
        self._progress_callback = callback

    def _make_opts(self, output_dir: Optional[Path] = None) -> dict:
        """Build yt-dlp options dict."""
        dest = output_dir or self.download_dir

        opts = {
            # Format selection — best audio available
            'format': 'bestaudio/best',

            # Output template — clean filenames
            'outtmpl': str(dest / '%(artist,uploader,channel)s - %(title)s [%(id)s].%(ext)s'),
            'restrictfilenames': False,
            'windowsfilenames': True,

            # Single track mode by default
            'noplaylist': True,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,

            # Post-processing: standardize to M4A
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.config.preferred_codec,
                    'preferredquality': self.config.preferred_quality,
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                },
                {
                    'key': 'EmbedThumbnail',
                },
            ],

            # Anti-detection / rate limiting
            'sleep_interval': self.config.sleep_min,
            'max_sleep_interval': self.config.sleep_max,
            'sleep_interval_requests': 1,
            'user_agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),

            # Write metadata files alongside audio
            'writethumbnail': True,
            'writeinfojson': False,
        }

        if self._progress_callback:
            opts['progress_hooks'] = [self._progress_hook]

        return opts

    def _progress_hook(self, d: dict):
        """Forward yt-dlp progress events to our callback."""
        if self._progress_callback:
            self._progress_callback({
                'status': d.get('status', 'unknown'),
                'percent': d.get('_percent_str', ''),
                'speed': d.get('_speed_str', ''),
                'eta': d.get('_eta_str', ''),
                'filename': d.get('filename', ''),
            })

    def is_downloaded(self, url: str) -> bool:
        """Check if URL was already downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM downloads WHERE url = ? AND status = 'ok'", (url,)
            ).fetchone()
            return row is not None

    def download(self, url: str, output_dir: Optional[Path] = None,
                 skip_existing: bool = True) -> DownloadResult:
        """Download a single URL. Returns DownloadResult."""

        if skip_existing and self.is_downloaded(url):
            logger.info(f"Already downloaded: {url}")
            return DownloadResult(
                success=True, url=url,
                error="Already in library (skipped)"
            )

        opts = self._make_opts(output_dir)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Extract info first to get metadata
                info = ydl.extract_info(url, download=True)

                if info is None:
                    raise RuntimeError("yt-dlp returned no info — URL may be invalid")

                artist = (info.get('artist') or info.get('uploader')
                          or info.get('channel') or 'Unknown')
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)

                # Find the actual downloaded file
                dest = output_dir or self.download_dir
                # yt-dlp may have renamed with postprocessing
                expected_stem = f"{artist} - {title}"
                filepath = self._find_downloaded_file(dest, info.get('id', ''))

                result = DownloadResult(
                    success=True,
                    artist=artist,
                    title=title,
                    filepath=str(filepath) if filepath else "",
                    url=url,
                )

                # Record in database
                self._record_download(url, artist, title, filepath, duration, info)
                return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed [{url}]: {error_msg}")
            self._record_error(url, error_msg)
            return DownloadResult(success=False, url=url, error=error_msg)

    def download_batch(self, urls: list, output_dir: Optional[Path] = None,
                       skip_existing: bool = True) -> list:
        """Download multiple URLs with rate limiting. Returns list of DownloadResult."""
        results = []
        total = len(urls)

        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url or url.startswith('#'):
                continue

            logger.info(f"[{i}/{total}] Downloading: {url}")
            result = self.download(url, output_dir, skip_existing)
            results.append(result)

            if i < total and result.success:
                # Ethical rate limiting between downloads
                time.sleep(self.config.sleep_min)

        return results

    def download_from_file(self, filepath: Path, output_dir: Optional[Path] = None) -> list:
        """Read URLs from a text file and batch download."""
        if not filepath.exists():
            raise FileNotFoundError(f"URL file not found: {filepath}")

        urls = [line.strip() for line in filepath.read_text().splitlines()
                if line.strip() and not line.strip().startswith('#')]

        return self.download_batch(urls, output_dir)

    def search_and_download(self, query: str, output_dir: Optional[Path] = None) -> DownloadResult:
        """Search YouTube/SoundCloud for a track and download the best match."""
        search_url = f"ytsearch1:{query}"
        return self.download(search_url, output_dir)

    def _find_downloaded_file(self, directory: Path, video_id: str) -> Optional[Path]:
        """Find the most recently created audio file matching a download."""
        codec = self.config.preferred_codec
        candidates = list(directory.glob(f"*{video_id}*.{codec}"))
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)

        # Fallback: most recently modified audio file
        all_audio = list(directory.glob(f"*.{codec}"))
        if all_audio:
            return max(all_audio, key=lambda p: p.stat().st_mtime)

        return None

    def _record_download(self, url, artist, title, filepath, duration, info):
        """Save download record to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                platform = info.get('extractor', info.get('extractor_key', 'unknown'))
                filesize = 0
                if filepath and Path(filepath).exists():
                    filesize = Path(filepath).stat().st_size

                conn.execute("""
                    INSERT OR REPLACE INTO downloads
                    (url, artist, title, filepath, codec, quality, filesize,
                     duration, source_platform, downloaded_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok')
                """, (
                    url, artist, title, str(filepath),
                    self.config.preferred_codec, self.config.preferred_quality,
                    filesize, duration, platform, datetime.now().isoformat(),
                ))
        except Exception as e:
            logger.warning(f"Failed to record download: {e}")

    def _record_error(self, url, error):
        """Log failed download to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO download_errors (url, error, attempted_at) VALUES (?, ?, ?)",
                    (url, error, datetime.now().isoformat())
                )
        except Exception:
            pass

    def get_download_stats(self) -> dict:
        """Return download statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM downloads WHERE status='ok'").fetchone()[0]
            errors = conn.execute("SELECT COUNT(*) FROM download_errors").fetchone()[0]
            total_size = conn.execute(
                "SELECT COALESCE(SUM(filesize), 0) FROM downloads WHERE status='ok'"
            ).fetchone()[0]
            platforms = conn.execute("""
                SELECT source_platform, COUNT(*)
                FROM downloads WHERE status='ok'
                GROUP BY source_platform
            """).fetchall()

        return {
            "total_downloaded": total,
            "total_errors": errors,
            "total_size_mb": round(total_size / (1024 * 1024), 1),
            "by_platform": dict(platforms),
        }
