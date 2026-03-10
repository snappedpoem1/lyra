"""Qobuz high-fidelity acquisition backend (Tier 1 â€” priority).

Uses qobuz-dl under the hood for authentication, app secret extraction,
stream URL signing, download, and metadata tagging. Falls back to the
Docker microservice if running, then to direct qobuz-dl API calls.

Quality: FLAC 24-bit/96kHz (fmt_id=7) by default, falls back to CD-quality
FLAC (fmt_id=6) if hi-res is unavailable for the track.

Requires: qobuz-dl (pip install qobuz-dl), requests
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from oracle.config import STAGING_FOLDER
from oracle.name_cleaner import clean_artist, clean_title as _clean_title

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGING_DIR = STAGING_FOLDER

def _get_qobuz_config() -> Dict[str, Any]:
    """Read Qobuz config at call time so .env values are always respected."""
    return {
        "username": os.getenv("QOBUZ_USERNAME", ""),
        "password": os.getenv("QOBUZ_PASSWORD", ""),
        "quality": int(os.getenv("QOBUZ_QUALITY", "7")),
        "service_url": os.getenv("QOBUZ_SERVICE_URL", "http://localhost:7700"),
    }

# Quality IDs: 5=MP3 320, 6=FLAC 16/44, 7=FLAC 24/96, 27=FLAC 24/192
QUALITY_LABELS = {5: "MP3 320k", 6: "FLAC 16/44", 7: "FLAC 24/96", 27: "FLAC 24/192"}

_ACQUIRER_LOCK = threading.Lock()


class QobuzAcquirer:
    """Qobuz acquisition backend powered by qobuz-dl.

    Handles the full lifecycle:
      1. Auto-extract app_id + secret from Qobuz web bundle
      2. Authenticate with email/password
      3. Search catalog and find best match
      4. Download FLAC with embedded metadata + cover art
      5. Move to staging for ingest watcher pickup
    """

    def __init__(
        self,
        email: str = "",
        password: str = "",
        quality: Optional[int] = None,
        staging_dir: Optional[Path] = None,
    ):
        _cfg = _get_qobuz_config()
        self.email = email or _cfg["username"]
        self.password = password or _cfg["password"]
        self.quality = quality if quality is not None else _cfg["quality"]
        self.staging_dir = staging_dir or STAGING_DIR
        self._client = None  # qopy.Client, lazy-initialized
        self._app_id: Optional[str] = None
        self._secrets: Optional[List[str]] = None
        self._init_lock = threading.Lock()

    # â”€â”€ Lazy Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _ensure_client(self) -> None:
        """Initialize the qobuz-dl client on first use.

        Extracts app_id/secrets from the Qobuz web bundle automatically,
        then authenticates. Cached for the lifetime of this instance.
        """
        if self._client is not None:
            return
        with self._init_lock:
            if self._client is not None:
                return

            from qobuz_dl.bundle import Bundle
            from qobuz_dl import qopy

            if not self._app_id:
                logger.info("[Qobuz] Extracting app credentials from web bundle...")
                bundle = Bundle()
                self._app_id = bundle.get_app_id()
                self._secrets = [s for s in bundle.get_secrets().values() if s]
                logger.info("[Qobuz] Got app_id=%s, %d secrets", self._app_id, len(self._secrets))

            logger.info("[Qobuz] Authenticating as %s...", self.email)
            self._client = qopy.Client(
                email=self.email,
                pwd=self.password,
                app_id=self._app_id,
                secrets=self._secrets,
            )
            logger.info("[Qobuz] Authenticated â€” subscription: %s", self._client.label)

    @property
    def client(self):
        """The authenticated qopy.Client instance."""
        self._ensure_client()
        return self._client

    # â”€â”€ Search + Match â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def search_tracks(
        self,
        artist: str,
        title: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search the Qobuz catalog for tracks.

        Args:
            artist: Artist name.
            title: Track title.
            limit: Max results.

        Returns:
            List of Qobuz track dicts.
        """
        query = f"{artist} {title}"
        resp = self.client.search_tracks(query, limit=limit)
        items = resp.get("tracks", {}).get("items", [])
        logger.debug("[Qobuz] Search '%s' â†’ %d results", query, len(items))
        return items

    def find_best_match(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching track using string similarity.

        Returns:
            Best matching track dict, or None if score < 0.55.
        """
        results = self.search_tracks(artist, title)
        if not results:
            return None

        scored: List[Tuple[float, Dict]] = []
        for track in results:
            t_artist = (track.get("performer", {}).get("name", "") or "").lower()
            t_title = (track.get("title", "") or "").lower()

            score = (
                SequenceMatcher(None, artist.lower(), t_artist).ratio() * 0.4
                + SequenceMatcher(None, title.lower(), t_title).ratio() * 0.6
            )
            if track.get("hires_streamable"):
                score += 0.05

            scored.append((score, track))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_track = scored[0]

        if best_score < 0.55:
            logger.info(
                "[Qobuz] Best match %.2f too low for '%s - %s'",
                best_score, artist, title,
            )
            return None

        logger.info(
            "[Qobuz] Matched: %s - %s (score=%.2f, id=%s, hires=%s)",
            best_track.get("performer", {}).get("name", "?"),
            best_track.get("title", "?"),
            best_score,
            best_track.get("id"),
            best_track.get("hires_streamable", False),
        )
        return best_track

    # â”€â”€ Download via qobuz-dl â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _download_with_qobuz_dl(
        self,
        track_id: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Use qobuz-dl's downloader for download + metadata + cover art.

        Args:
            track_id: Qobuz track ID (as string).
            output_dir: Directory to download into.

        Returns:
            Path to the downloaded file, or None on failure.
        """
        from qobuz_dl import downloader

        d = downloader.Download(
            client=self.client,
            item_id=track_id,
            path=str(output_dir),
            quality=self.quality,
            embed_art=True,
            downgrade_quality=True,
            no_cover=False,  # Download cover.jpg so embed_art can use it
            folder_format="{artist} - {album}",
            track_format="{tracknumber}. {tracktitle}",
        )
        d.download_id_by_type(track=True)

        # Clean up cover.jpg files â€” art is embedded in the audio file
        for cover in output_dir.rglob("cover.jpg"):
            cover.unlink(missing_ok=True)

        # Find what was downloaded â€” qobuz-dl creates artist-album subdirs
        audio_exts = {".flac", ".mp3", ".m4a", ".ogg"}
        candidates = [
            p for p in output_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in audio_exts
        ]

        if not candidates:
            return None

        # Return the most recently created file
        return max(candidates, key=lambda p: p.stat().st_mtime)

    # â”€â”€ Full Acquisition Pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def acquire(
        self,
        artist: str,
        title: str,
    ) -> Dict[str, Any]:
        """Full pipeline: search â†’ match â†’ download â†’ tag â†’ stage.

        Args:
            artist: Artist name.
            title: Track title.

        Returns:
            Result dict compatible with the waterfall pipeline.
        """
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()

        try:
            # 1. Find best match
            match = self.find_best_match(artist, title)
            if not match:
                return {
                    "success": False,
                    "error": "No matching track found on Qobuz",
                    "tier": 1,
                    "source": "qobuz",
                    "elapsed": time.perf_counter() - start,
                }

            track_id = str(match["id"])
            matched_artist = match.get("performer", {}).get("name", artist)
            matched_title = match.get("title", title)

            # 2. Get stream info for metadata (bit_depth, sampling_rate)
            try:
                url_info = self.client.get_track_url(track_id, self.quality)
                bit_depth = url_info.get("bit_depth", "?")
                sampling_rate = url_info.get("sampling_rate", "?")
            except Exception:
                bit_depth = "?"
                sampling_rate = "?"

            # 3. Download with qobuz-dl (handles tagging + cover art)
            with tempfile.TemporaryDirectory(prefix="qobuz_", dir=self.staging_dir.parent) as tmp:
                tmp_path = Path(tmp)
                downloaded = self._download_with_qobuz_dl(track_id, tmp_path)

                if not downloaded:
                    return {
                        "success": False,
                        "error": "qobuz-dl produced no output file",
                        "tier": 1,
                        "source": "qobuz",
                        "elapsed": time.perf_counter() - start,
                    }

                # 4. Rename to clean Artist - Title format and move to staging
                ext = downloaded.suffix
                clean_a, _ = clean_artist(matched_artist)
                clean_t, _ = _clean_title(matched_title)
                # Sanitise for filesystem (spaces kept — staging is intermediate)
                clean_a = re.sub(r'[<>:"/\\|?*]', '_', clean_a)
                clean_t = re.sub(r'[<>:"/\\|?*]', '_', clean_t)
                filename = f"{clean_a} - {clean_t}{ext}"

                target = self.staging_dir / filename
                if target.exists():
                    target = self.staging_dir / f"{Path(filename).stem}_{int(time.time())}{ext}"

                final_path = shutil.move(str(downloaded), str(target))

            elapsed = time.perf_counter() - start
            logger.info(
                "[Qobuz] Acquired: %s - %s (%sbit/%skHz, %.1fs)",
                matched_artist, matched_title, bit_depth, sampling_rate, elapsed,
            )

            return {
                "success": True,
                "path": str(final_path),
                "tier": 1,
                "source": "qobuz",
                "artist": matched_artist,
                "title": matched_title,
                "elapsed": elapsed,
                "metadata": {
                    "qobuz_id": int(track_id),
                    "bit_depth": bit_depth,
                    "sampling_rate": sampling_rate,
                    "format": ext.lstrip("."),
                    "quality_label": QUALITY_LABELS.get(self.quality, "unknown"),
                },
            }

        except Exception as exc:
            logger.exception("[Qobuz] Acquisition error")
            return {
                "success": False,
                "error": str(exc),
                "tier": 1,
                "source": "qobuz",
                "elapsed": time.perf_counter() - start,
            }


# â”€â”€ Module-level convenience API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_acquirer: Optional[QobuzAcquirer] = None


def _get_acquirer() -> QobuzAcquirer:
    """Get or create the singleton acquirer."""
    global _acquirer
    if _acquirer is None:
        with _ACQUIRER_LOCK:
            if _acquirer is None:
                _acquirer = QobuzAcquirer()
    return _acquirer


def is_available() -> bool:
    """Check if Qobuz credentials are configured (username + password).

    app_id and app_secret are auto-extracted â€” only user creds needed.
    """
    _cfg = _get_qobuz_config()
    return bool(_cfg["username"] and _cfg["password"])


def is_service_available() -> bool:
    """Check if the Dockerised Qobuz microservice is running."""
    try:
        resp = requests.get(f"{_get_qobuz_config()['service_url']}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def download(artist: str, title: str) -> Dict[str, Any]:
    """Acquire a track via Qobuz. Tries Docker service first, then direct.

    Returns:
        Result dict with success, path, error, tier, source keys.
    """
    # Prefer the containerised microservice if it's up
    if is_service_available():
        return _download_via_service(artist, title)

    # Direct qobuz-dl
    if not is_available():
        return {
            "success": False,
            "error": "Qobuz credentials not configured (set QOBUZ_USERNAME + QOBUZ_PASSWORD)",
            "tier": 1,
            "source": "qobuz",
        }

    return _get_acquirer().acquire(artist, title)


def _download_via_service(artist: str, title: str) -> Dict[str, Any]:
    """Call the Dockerised microservice to acquire the track."""
    try:
        service_url = _get_qobuz_config()["service_url"]
        resp = requests.post(
            f"{service_url}/acquire",
            json={"artist": artist, "title": title},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()

        # Translate container path â†’ host path
        if data.get("success") and data.get("path"):
            data["path"] = str(STAGING_DIR / Path(data["path"]).name)

        return data

    except Exception as exc:
        logger.warning("[Qobuz] Service call failed: %s", exc)
        return {
            "success": False,
            "error": f"Qobuz service error: {exc}",
            "tier": 1,
            "source": "qobuz",
        }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 3:
        print("Usage: python -m oracle.acquirers.qobuz <artist> <title>")
        print(f"\nQobuz available: {is_available()}")
        print(f"Service running: {is_service_available()}")
        sys.exit(0)

    result = download(sys.argv[1], sys.argv[2])
    print(result)
