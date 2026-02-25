"""Unified acquisition search (multi-source).

Priority 5A: one query, multiple sources.

v1 sources:
- prowlarr (existing adapter)
- youtube via yt-dlp search (ytsearch)

This module returns unified, ranked results but does NOT automatically enqueue.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

import yt_dlp

from oracle.acquirers.prowlarr_rd import search_prowlarr

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionResult:
    title: str
    artist: str
    album: str
    source: str
    source_url: str
    quality: str
    format: str
    size_mb: float
    cached: bool
    seeds: int
    confidence: float
    already_owned: bool


def _rank_key(r: AcquisitionResult) -> tuple:
    # Higher is better; sort desc.
    quality_score = 0
    q = (r.quality or "").upper()
    if "FLAC" in q:
        quality_score = 4
    elif "320" in q:
        quality_score = 3
    elif "V0" in q:
        quality_score = 2
    elif "256" in q:
        quality_score = 1

    return (
        float(r.confidence or 0.0),
        quality_score,
        1 if r.cached else 0,
        int(r.seeds or 0),
        -1 if r.already_owned else 0,
    )


def _ytsearch(query: str, limit: int = 5) -> List[AcquisitionResult]:
    q = (query or "").strip()
    if not q:
        return []

    limit = max(1, min(int(limit or 5), 20))

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": True,
        "skip_download": True,
    }

    results: List[AcquisitionResult] = []
    search_expr = f"ytsearch{limit}:{q}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_expr, download=False)
    except Exception:
        logger.exception("yt-dlp search failed")
        return []

    entries = (info or {}).get("entries") or []
    for e in entries:
        if not e:
            continue
        title = str(e.get("title") or "").strip() or "Unknown"
        url = str(e.get("url") or e.get("webpage_url") or "").strip()
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"

        uploader = str(e.get("uploader") or e.get("channel") or "").strip()
        results.append(
            AcquisitionResult(
                title=title,
                artist=uploader or "",
                album="",
                source="youtube",
                source_url=url,
                quality="best",
                format="audio",
                size_mb=0.0,
                cached=False,
                seeds=0,
                confidence=0.6,
                already_owned=False,
            )
        )

    return results


def _prowlarr_search(query: str, limit: int = 10) -> List[AcquisitionResult]:
    q = (query or "").strip()
    if not q:
        return []

    try:
        raw = search_prowlarr(q, limit=limit)
    except Exception:
        logger.exception("Prowlarr search failed")
        return []

    results: List[AcquisitionResult] = []
    for item in raw or []:
        title = str(item.get("title") or "Unknown")
        link = (
            item.get("magnetUrl")
            or item.get("downloadUrl")
            or item.get("link")
            or item.get("guid")
            or ""
        )
        seeds = int(item.get("seeders") or 0) if str(item.get("seeders") or "").isdigit() else 0
        size = float(item.get("size") or 0.0)
        size_mb = size / (1024 * 1024) if size else 0.0
        results.append(
            AcquisitionResult(
                title=title,
                artist="",
                album="",
                source="prowlarr",
                source_url=str(link),
                quality="unknown",
                format="nzb/torrent",
                size_mb=size_mb,
                cached=False,
                seeds=seeds,
                confidence=0.7,
                already_owned=False,
            )
        )

    return results


async def search_all_sources(query: str, sources: Optional[List[str]] = None, limit: int = 10) -> List[AcquisitionResult]:
    """Search across configured acquisition sources concurrently."""
    srcs = [s.lower() for s in (sources or ["youtube", "prowlarr"]) if s]
    limit = max(1, min(int(limit or 10), 50))

    tasks = []
    if "youtube" in srcs:
        tasks.append(asyncio.to_thread(_ytsearch, query, min(10, limit)))
    if "prowlarr" in srcs:
        tasks.append(asyncio.to_thread(_prowlarr_search, query, min(20, limit)))

    if not tasks:
        return []

    batches = await asyncio.gather(*tasks, return_exceptions=True)
    flat: List[AcquisitionResult] = []
    for b in batches:
        if isinstance(b, Exception):
            continue
        flat.extend(b)

    flat.sort(key=_rank_key, reverse=True)
    return flat[:limit]
