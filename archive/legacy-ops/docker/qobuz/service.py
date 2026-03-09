"""Qobuz acquisition microservice (Docker).

FastAPI service wrapping qobuz-dl for the Oracle acquisition pipeline.
Receives track requests via POST /acquire, downloads hi-fi audio with
full metadata + cover art, and writes to the staging volume mount.

The waterfall pipeline calls this service over HTTP when it's running.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("qobuz-service")

# ── Configuration from environment ──────────────────────────────────

QOBUZ_USERNAME = os.getenv("QOBUZ_USERNAME", "")
QOBUZ_PASSWORD = os.getenv("QOBUZ_PASSWORD", "")
STAGING_DIR = Path(os.getenv("STAGING_DIR", "/app/staging"))
QUALITY = int(os.getenv("QOBUZ_QUALITY", "7"))
MAX_WORKERS = int(os.getenv("QOBUZ_MAX_WORKERS", "3"))

QUALITY_LABELS = {5: "MP3 320k", 6: "FLAC 16/44", 7: "FLAC 24/96", 27: "FLAC 24/192"}


# ── Qobuz-dl client management ─────────────────────────────────────

_client = None
_client_lock = None


def get_client():
    """Get or create the authenticated qobuz-dl client.

    Auto-extracts app_id and secrets from the Qobuz web bundle,
    then authenticates with user credentials.
    """
    global _client
    if _client is not None:
        return _client

    from qobuz_dl.bundle import Bundle
    from qobuz_dl import qopy

    logger.info("Extracting app credentials from Qobuz web bundle...")
    bundle = Bundle()
    app_id = bundle.get_app_id()
    secrets = [s for s in bundle.get_secrets().values() if s]
    logger.info("Got app_id=%s, %d secrets", app_id, len(secrets))

    logger.info("Authenticating as %s...", QOBUZ_USERNAME)
    _client = qopy.Client(
        email=QOBUZ_USERNAME,
        pwd=QOBUZ_PASSWORD,
        app_id=app_id,
        secrets=secrets,
    )
    logger.info("Authenticated — subscription: %s", _client.label)
    return _client


def find_best_match(
    artist: str,
    title: str,
    limit: int = 5,
) -> Optional[Dict[str, Any]]:
    """Search Qobuz and return the best matching track."""
    client = get_client()
    query = f"{artist} {title}"
    resp = client.search_tracks(query, limit=limit)
    items = resp.get("tracks", {}).get("items", [])

    if not items:
        return None

    scored: List[Tuple[float, Dict]] = []
    for track in items:
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
    return best_track if best_score >= 0.55 else None


def download_track(track_id: str, output_dir: Path) -> Optional[Path]:
    """Download a track using qobuz-dl's downloader (handles tagging + art)."""
    from qobuz_dl import downloader

    d = downloader.Download(
        client=get_client(),
        item_id=track_id,
        path=str(output_dir),
        quality=QUALITY,
        embed_art=True,
        downgrade_quality=True,
        no_cover=False,
        folder_format="{artist} - {album}",
        track_format="{tracknumber}. {tracktitle}",
    )
    d.download_id_by_type(track=True)

    # Clean up cover.jpg — art is embedded in the audio file
    for cover in output_dir.rglob("cover.jpg"):
        cover.unlink(missing_ok=True)

    audio_exts = {".flac", ".mp3", ".m4a", ".ogg"}
    candidates = [
        p for p in output_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in audio_exts
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


# ── FastAPI App ─────────────────────────────────────────────────────

app = FastAPI(title="Lyra Qobuz Acquirer", version="2.0.0")
_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)


class AcquireRequest(BaseModel):
    artist: str
    title: str
    quality: Optional[int] = None


class AcquireResponse(BaseModel):
    success: bool
    path: Optional[str] = None
    artist: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    tier: int = 2
    source: str = "qobuz"
    elapsed: float = 0.0
    metadata: Dict[str, Any] = {}


class BatchRequest(BaseModel):
    tracks: List[AcquireRequest]


class BatchResponse(BaseModel):
    results: List[AcquireResponse]
    succeeded: int
    failed: int
    elapsed: float


@app.get("/health")
def health():
    """Health check for Docker and waterfall availability probe."""
    configured = bool(QOBUZ_USERNAME and QOBUZ_PASSWORD)
    return {
        "status": "ok" if configured else "unconfigured",
        "configured": configured,
        "staging_dir": str(STAGING_DIR),
        "quality": QUALITY,
        "quality_label": QUALITY_LABELS.get(QUALITY, "unknown"),
    }


@app.post("/acquire", response_model=AcquireResponse)
def acquire_track(req: AcquireRequest) -> AcquireResponse:
    """Acquire a single track: search → download → tag → stage."""
    start = time.perf_counter()

    try:
        # 1. Match
        match = find_best_match(req.artist, req.title)
        if not match:
            return AcquireResponse(
                success=False,
                error="No matching track on Qobuz",
                elapsed=time.perf_counter() - start,
            )

        track_id = str(match["id"])
        matched_artist = match.get("performer", {}).get("name", req.artist)
        matched_title = match.get("title", req.title)

        # 2. Get stream info for metadata
        try:
            url_info = get_client().get_track_url(track_id, req.quality or QUALITY)
            bit_depth = url_info.get("bit_depth", "?")
            sampling_rate = url_info.get("sampling_rate", "?")
        except Exception:
            bit_depth = "?"
            sampling_rate = "?"

        # 3. Download with qobuz-dl
        with tempfile.TemporaryDirectory(prefix="qobuz_") as tmp:
            tmp_path = Path(tmp)
            downloaded = download_track(track_id, tmp_path)

            if not downloaded:
                return AcquireResponse(
                    success=False,
                    error="qobuz-dl produced no output file",
                    elapsed=time.perf_counter() - start,
                )

            # 4. Rename and move to staging
            ext = downloaded.suffix
            clean_a = re.sub(r'[<>:"/\\|?*]', '_', matched_artist)
            clean_t = re.sub(r'[<>:"/\\|?*]', '_', matched_title)
            filename = f"{clean_a} - {clean_t}{ext}"

            target = STAGING_DIR / filename
            if target.exists():
                target = STAGING_DIR / f"{Path(filename).stem}_{int(time.time())}{ext}"
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            final = shutil.move(str(downloaded), str(target))

        elapsed = time.perf_counter() - start
        return AcquireResponse(
            success=True,
            path=str(final),
            artist=matched_artist,
            title=matched_title,
            elapsed=elapsed,
            metadata={
                "qobuz_id": int(track_id),
                "bit_depth": bit_depth,
                "sampling_rate": sampling_rate,
                "format": ext.lstrip("."),
                "quality_label": QUALITY_LABELS.get(req.quality or QUALITY, "unknown"),
            },
        )

    except Exception as exc:
        logger.exception("Acquisition failed")
        return AcquireResponse(
            success=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


@app.post("/acquire/batch", response_model=BatchResponse)
def acquire_batch(req: BatchRequest) -> BatchResponse:
    """Acquire multiple tracks concurrently via thread pool."""
    start = time.perf_counter()

    futures = [_pool.submit(acquire_track, t) for t in req.tracks]
    results = [f.result() for f in futures]

    succeeded = sum(1 for r in results if r.success)
    return BatchResponse(
        results=results,
        succeeded=succeeded,
        failed=len(results) - succeeded,
        elapsed=time.perf_counter() - start,
    )


@app.get("/search")
def search(artist: str, title: str, limit: int = 5):
    """Search Qobuz catalog without downloading."""
    client = get_client()
    resp = client.search_tracks(f"{artist} {title}", limit=limit)
    items = resp.get("tracks", {}).get("items", [])
    return {
        "query": f"{artist} - {title}",
        "count": len(items),
        "tracks": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "artist": t.get("performer", {}).get("name"),
                "album": t.get("album", {}).get("title"),
                "duration": t.get("duration"),
                "hires": t.get("hires_streamable", False),
                "bit_depth": t.get("maximum_bit_depth"),
                "sampling_rate": t.get("maximum_sampling_rate"),
            }
            for t in items
        ],
    }
