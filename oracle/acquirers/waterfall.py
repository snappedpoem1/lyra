"""Unified Acquisition Waterfall.

Lyra's tiered acquisition strategy:
  T1: Qobuz       (hi-fi streaming API -> FLAC up to 24-bit/96kHz)
  T2: Streamrip   (alternative hi-fi ripper fallback)
  T3: Slskd       (peer-to-peer FLAC search via Soulseek)
  T4: Real-Debrid (Prowlarr search -> RD cache -> direct download)
  T5: SpotDL      (YouTube with Spotify metadata - final fallback)

Each tier gracefully degrades if services aren't running.
Quality: FLAC hi-res (T1/T2) -> FLAC (T3/T4) -> 320k MP3 (T5)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from oracle.config import guard_bypass_allowed, guard_bypass_reason
from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)
MIN_GUARD_CONFIDENCE = 0.30


def _emit(event: Dict[str, Any]) -> None:
    """Emit a structured JSON phase event to stdout for Rust to consume."""
    print(json.dumps(event), flush=True)


@dataclass
class AcquisitionResult:
    """Result of an acquisition attempt."""
    success: bool
    tier: int
    source: str
    path: Optional[str] = None
    artist: str = ""
    title: str = ""
    error: Optional[str] = None
    elapsed: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# --- Availability Checks ---------------------------------------------------


def _check_qobuz_available() -> bool:
    """Check if Qobuz credentials are configured or Docker service is up."""
    try:
        from oracle.acquirers.qobuz import is_service_available, is_available
        return is_service_available() or is_available()
    except ImportError:
        return False


def _check_slskd_available() -> bool:
    """Check if Slskd node is reachable."""
    import requests
    url = os.getenv("LYRA_PROTOCOL_NODE_URL", "http://localhost:5030")
    try:
        response = requests.get(f"{url}/api/v0/application", timeout=5)
        return response.status_code in (200, 401)  # 401 = needs auth but running
    except Exception:
        return False


def _check_streamrip_available() -> bool:
    """Check if streamrip CLI is available."""
    try:
        from oracle.acquirers.streamrip import is_available

        return is_available()
    except ImportError:
        return False


def _check_prowlarr_available() -> bool:
    """Check if Prowlarr is reachable."""
    import requests
    url = os.getenv("PROWLARR_URL", "http://localhost:9696")
    api_key = os.getenv("PROWLARR_API_KEY")
    if not api_key:
        return False
    try:
        response = requests.get(
            f"{url}/api/v1/health",
            headers={"X-Api-Key": api_key},
            timeout=5,
        )
        return response.status_code == 200
    except Exception:
        return False


def _check_realdebrid_available() -> bool:
    """Check if Real-Debrid API is accessible."""
    key = os.getenv("REAL_DEBRID_KEY") or os.getenv("REAL_DEBRID_API_KEY")
    if not key:
        return False
    try:
        import requests
        response = requests.get(
            "https://api.real-debrid.com/rest/1.0/user",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        return response.status_code == 200
    except Exception:
        return False


def _check_spotdl_available() -> bool:
    """Check if spotdl is installed."""
    try:
        from oracle.acquirers.spotdl import is_available

        return is_available()
    except ImportError:
        return False


# --- Tier Implementations ---------------------------------------------------


def _try_tier1_qobuz(artist: str, title: str) -> AcquisitionResult:
    """Tier 1: Qobuz hi-fi (FLAC up to 24-bit/96kHz, authenticated API)."""
    start = time.perf_counter()

    if not _check_qobuz_available():
        return AcquisitionResult(
            success=False,
            tier=1,
            source="qobuz",
            error="Qobuz not available",
            elapsed=time.perf_counter() - start,
        )

    try:
        from oracle.acquirers.qobuz import download

        result = download(artist, title)

        return AcquisitionResult(
            success=result.get("success", False),
            tier=1,
            source="qobuz",
            path=result.get("path"),
            artist=result.get("artist", artist),
            title=result.get("title", title),
            error=result.get("error"),
            elapsed=result.get("elapsed", time.perf_counter() - start),
            metadata=result.get("metadata", {}),
        )

    except Exception as e:
        logger.exception("[T1] Qobuz error")
        return AcquisitionResult(
            success=False,
            tier=1,
            source="qobuz",
            error=str(e),
            elapsed=time.perf_counter() - start,
        )


def _try_tier2_streamrip(artist: str, title: str, album: Optional[str] = None) -> AcquisitionResult:
    """Tier 2: Streamrip fallback (if configured)."""
    start = time.perf_counter()
    if not _check_streamrip_available():
        return AcquisitionResult(
            success=False,
            tier=2,
            source="streamrip",
            error="Streamrip not available",
            elapsed=time.perf_counter() - start,
        )

    try:
        from oracle.acquirers.streamrip import download

        result = download(artist, title, album=album)
        return AcquisitionResult(
            success=result.get("success", False),
            tier=2,
            source="streamrip",
            path=result.get("path"),
            artist=result.get("artist", artist),
            title=result.get("title", title),
            error=result.get("error"),
            elapsed=result.get("elapsed", time.perf_counter() - start),
            metadata=result.get("metadata", {}),
        )

    except Exception as e:
        logger.exception("[T2] Streamrip error")
        return AcquisitionResult(
            success=False,
            tier=2,
            source="streamrip",
            error=str(e),
            elapsed=time.perf_counter() - start,
        )


def _try_tier3_slskd(artist: str, title: str) -> AcquisitionResult:
    """Tier 3: Slskd peer-to-peer (FLAC quality)."""
    start = time.perf_counter()

    if not _check_slskd_available():
        return AcquisitionResult(
            success=False,
            tier=3,
            source="slskd",
            error="Slskd not available",
            elapsed=time.perf_counter() - start,
        )

    try:
        from oracle.lyra_protocol import run_lyra_protocol
        import asyncio
        import concurrent.futures

        # asyncio.run() raises RuntimeError if called from inside a running event
        # loop (e.g. pytest-asyncio, Jupyter). Fall back to a dedicated thread
        # with its own loop to stay safe in both sync and async call contexts.
        def _run_sync():
            return asyncio.run(run_lyra_protocol(artist, title))

        try:
            asyncio.get_running_loop()
            # Already in a running loop — run in a worker thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _tp:
                result = _tp.submit(_run_sync).result(timeout=120)
        except RuntimeError:
            # No running loop — safe to call asyncio.run() directly
            result = _run_sync()

        if result.get("status") == "queued":
            # "queued" means slskd has scheduled the download, not that the file
            # exists yet.  Returning success=True here would mark the queue item
            # completed before the file materialises, producing stuck entries.
            # Return failure so the caller can retry or escalate to T4/T5.
            return AcquisitionResult(
                success=False,
                tier=3,
                source="slskd",
                error="slskd queued but file not yet materialised",
                artist=artist,
                title=title,
                elapsed=time.perf_counter() - start,
                metadata={
                    "queued": True,
                    "route": result.get("route"),
                    "integrity_score": result.get("winner") and getattr(result.get("winner"), "integrity_score", None),
                },
            )

        return AcquisitionResult(
            success=False,
            tier=3,
            source="slskd",
            error=result.get("error", "No results"),
            elapsed=time.perf_counter() - start,
        )

    except Exception as e:
        logger.exception("[T3] Slskd error")
        return AcquisitionResult(
            success=False,
            tier=3,
            source="slskd",
            error=str(e),
            elapsed=time.perf_counter() - start,
        )


# Backward-compatible alias for older tests/callers written before Slskd was
# moved from tier 2 to tier 3 in the waterfall ordering.
def _try_tier2_slskd(artist: str, title: str) -> AcquisitionResult:
    return _try_tier3_slskd(artist, title)


def _try_tier4_realdebrid(artist: str, title: str, album: Optional[str] = None) -> AcquisitionResult:
    """Tier 4: Prowlarr -> Real-Debrid (cached torrents, FLAC quality)."""
    start = time.perf_counter()

    if not _check_prowlarr_available():
        return AcquisitionResult(
            success=False,
            tier=4,
            source="real_debrid",
            error="Prowlarr not available",
            elapsed=time.perf_counter() - start,
        )

    if not _check_realdebrid_available():
        return AcquisitionResult(
            success=False,
            tier=4,
            source="real_debrid",
            error="Real-Debrid not available",
            elapsed=time.perf_counter() - start,
        )

    try:
        from oracle.acquirers.prowlarr_rd import search_prowlarr
        from oracle.acquirers.realdebrid import (
            extract_hash_from_magnet,
            probe_magnet_cached,
        )
        from oracle.acquirers.guard import guard_file

        # Search for release (prefer FLAC)
        query = f"{artist} {album or title} FLAC"
        logger.info(f"[T4] Searching Prowlarr: {query}")
        results = search_prowlarr(query, limit=10)

        if not results:
            query = f"{artist} {title}"
            results = search_prowlarr(query, limit=10)

        if not results:
            return AcquisitionResult(
                success=False,
                tier=4,
                source="real_debrid",
                error="No results from Prowlarr",
                elapsed=time.perf_counter() - start,
            )

        # Build magnet list from Prowlarr results.
        # Prowlarr field map (verified empirically):
        #   guid      = actual magnet URI ("magnet:?xt=urn:btih:...") for TPB-style indexers
        #   infoHash  = raw hex hash (most reliable -- use to construct magnet if guid isn't one)
        #   magnetUrl = Prowlarr proxy URL (do NOT send this to RD; use guid/infoHash instead)
        magnets: List[Dict] = []
        for r in results:
            info_hash = (r.get("infoHash") or "").strip().lower()
            magnet = ""

            guid = (r.get("guid") or "").strip()
            if guid.lower().startswith("magnet:"):
                magnet = guid
                if not info_hash:
                    info_hash = extract_hash_from_magnet(magnet) or ""
            elif info_hash:
                dn = (r.get("title") or "").replace(" ", "+")
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"

            if magnet:
                magnets.append({
                    "magnet": magnet,
                    "title": r.get("title", ""),
                    "is_flac": "flac" in (r.get("title") or "").lower(),
                    "seeders": r.get("seeders", 0) or 0,
                })

        if not magnets:
            return AcquisitionResult(
                success=False,
                tier=4,
                source="real_debrid",
                error="No usable magnets in Prowlarr results",
                elapsed=time.perf_counter() - start,
            )

        # Sort: FLAC first, then by seeder count descending
        magnets.sort(key=lambda x: (not x["is_flac"], -x["seeders"]))

        # RD instantAvailability is deprecated (returns 403). Instead: add each
        # magnet, poll for 20s. Cached torrents go to "downloaded" in <5s.
        # Non-cached ones time out -- we delete them and move on.
        # Limit to top 3 to keep T4 bounded (<60s total before falling to T5).
        for entry in magnets[:3]:
            magnet = entry["magnet"]
            label = entry["title"][:55] or magnet[:55]
            logger.info(f"[T4] Probing RD cache: {label}")
            try:
                files = probe_magnet_cached(
                    magnet,
                    target_artist=artist,
                    target_title=title,
                )
                if not files:
                    continue

                # Post-download guard: verify the file is plausibly the right track
                audio_files = [
                    f for f in files
                    if f.suffix.lower() in {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus"}
                ]
                if not audio_files:
                    logger.debug("[T4] No audio files in download -- skipping")
                    continue

                best_file = audio_files[0]
                if len(audio_files) > 1:
                    # Pick the file whose name best matches the target
                    from difflib import SequenceMatcher
                    target_str = f"{artist} {title}".lower()
                    audio_files.sort(
                        key=lambda p: SequenceMatcher(None, target_str, p.stem.lower()).ratio(),
                        reverse=True,
                    )
                    best_file = audio_files[0]

                guard_result = guard_file(best_file)
                if not guard_result.allowed:
                    logger.info(
                        "[T4] Guard rejected downloaded file: %s (%s)",
                        best_file.name,
                        guard_result.rejection_reason or "rejected",
                    )
                    continue
                if guard_result.confidence < MIN_GUARD_CONFIDENCE:
                    logger.info(
                        "[T4] Guard low confidence %.2f for %s",
                        guard_result.confidence,
                        best_file.name,
                    )
                    continue

                return AcquisitionResult(
                    success=True,
                    tier=4,
                    source="real_debrid",
                    path=str(best_file),
                    artist=artist,
                    title=title,
                    elapsed=time.perf_counter() - start,
                    metadata={"is_flac": entry["is_flac"], "files": len(files)},
                )
            except Exception as e:
                logger.debug(f"[T4] probe failed: {e}")

        return AcquisitionResult(
            success=False,
            tier=4,
            source="real_debrid",
            error="No cached results found in Real-Debrid",
            elapsed=time.perf_counter() - start,
        )

    except Exception as e:
        logger.exception("[T4] Real-Debrid error")
        return AcquisitionResult(
            success=False,
            tier=4,
            source="real_debrid",
            error=str(e),
            elapsed=time.perf_counter() - start,
        )


def _try_tier5_spotdl(artist: str, title: str, spotify_uri: Optional[str] = None) -> AcquisitionResult:
    """Tier 5: SpotDL (YouTube with Spotify metadata, 320k quality)."""
    start = time.perf_counter()

    try:
        from oracle.acquirers.spotdl import download, is_available

        if not is_available():
            return AcquisitionResult(
                success=False,
                tier=5,
                source="spotdl",
                error="spotdl not installed or bundled",
                elapsed=time.perf_counter() - start,
            )

        result = download(artist, title, spotify_uri)

        return AcquisitionResult(
            success=result.get("success", False),
            tier=5,
            source="spotdl",
            path=result.get("path"),
            artist=artist,
            title=title,
            error=result.get("error"),
            elapsed=time.perf_counter() - start,
        )

    except Exception as e:
        logger.exception("[T5] SpotDL error")
        return AcquisitionResult(
            success=False,
            tier=5,
            source="spotdl",
            error=str(e),
            elapsed=time.perf_counter() - start,
        )


# Backward-compatible alias for older tests/callers written before SpotDL was
# moved from tier 4 to tier 5 in the waterfall ordering.
def _try_tier4_spotdl(artist: str, title: str, spotify_uri: Optional[str] = None) -> AcquisitionResult:
    return _try_tier5_spotdl(artist, title, spotify_uri)


# --- Guard ------------------------------------------------------------------


def _guard_check(artist: str, title: str, skip_guard: bool = False) -> Dict[str, Any]:
    """Run pre-acquisition guard check."""
    if skip_guard:
        if not guard_bypass_allowed():
            logger.error(
                "[guard] Skip requested but LYRA_ALLOW_GUARD_BYPASS is not enabled for %s - %s",
                artist,
                title,
            )
            return {
                "allowed": False,
                "artist": artist,
                "title": title,
                "reason": "Guard bypass denied: set LYRA_ALLOW_GUARD_BYPASS=1",
                "category": "policy",
            }
        logger.warning(
            "[guard] BYPASS ENABLED for %s - %s (reason=%s)",
            artist,
            title,
            guard_bypass_reason(),
        )
        return {"allowed": True, "artist": artist, "title": title}

    try:
        from oracle.acquirers.guard import guard_acquisition

        result = guard_acquisition(
            artist=artist,
            title=title,
            skip_validation=False,  # Full validation
            skip_duplicate_check=False,
        )

        return {
            "allowed": result.allowed,
            "artist": result.artist,
            "title": result.title,
            "album": result.album,
            "reason": result.rejection_reason,
            "category": result.rejection_category,
            "confidence": result.confidence,
            "validated_by": result.validated_by,
            "warnings": result.warnings,
        }
    except ImportError:
        logger.error("Guard module not available; failing closed")
        return {
            "allowed": False,
            "artist": artist,
            "title": title,
            "reason": "Guard module unavailable",
            "category": "guard_error",
        }
    except Exception as e:
        logger.error("Guard check failed; failing closed: %s", e)
        return {
            "allowed": False,
            "artist": artist,
            "title": title,
            "reason": f"Guard check failed: {e}",
            "category": "guard_error",
        }


# --- Main Waterfall ---------------------------------------------------------


def acquire(
    artist: str,
    title: str,
    album: Optional[str] = None,
    spotify_uri: Optional[str] = None,
    skip_tiers: Optional[List[int]] = None,
    max_tier: int = 5,
    skip_guard: bool = False,
    pre_validated: bool = False,
) -> AcquisitionResult:
    """Run the acquisition waterfall with guard protection.

    Tries each tier in order:
      T1 (Qobuz) -> T2 (Streamrip) -> T3 (Slskd) -> T4 (Real-Debrid) -> T5 (SpotDL)

    GUARD CHECK runs first to reject:
    - Karaoke/tribute/cover versions
    - Record labels as artists
    - YouTube channels as artists
    - Duplicates already in library

    Args:
        artist: Artist name
        title: Track title
        album: Optional album name (helps T4 search)
        spotify_uri: Optional Spotify URI (helps T5)
        skip_tiers: List of tier numbers to skip
            (1=Qobuz, 2=Streamrip, 3=Slskd, 4=RD, 5=SpotDL)
        max_tier: Stop after this tier (1-5)
        skip_guard: Skip guard check (requires LYRA_ALLOW_GUARD_BYPASS=1)
        pre_validated: Skip guard because caller already validated.
            Unlike skip_guard, this does not require the bypass env var.
            Use when smart_pipeline has already run its own validation.

    Returns:
        AcquisitionResult from the first successful tier, or the last failure
    """
    skip_tiers = skip_tiers or []
    attempts: List[AcquisitionResult] = []
    waterfall_start = time.perf_counter()

    logger.info(f"[Waterfall] {artist} - {title}")

    # GUARD CHECK - reject junk before wasting bandwidth
    if pre_validated:
        guard = {"allowed": True, "artist": artist, "title": title}
    else:
        guard = _guard_check(artist, title, skip_guard)

    if not guard.get("allowed"):
        logger.warning(f"  [GUARD REJECTED] {guard.get('reason')}")
        _emit({"event": "failure", "error": f"Guard rejected: {guard.get('reason')}", "elapsed": time.perf_counter() - waterfall_start})
        return AcquisitionResult(
            success=False,
            tier=0,
            source="guard",
            error=f"Guard rejected: {guard.get('reason')}",
            artist=artist,
            title=title,
            metadata={"rejection_category": guard.get("category")},
        )

    # Use cleaned metadata from guard
    artist = guard.get("artist", artist)
    title = guard.get("title", title)
    if guard.get("album") and not album:
        album = guard.get("album")

    if guard.get("warnings"):
        for w in guard.get("warnings", []):
            logger.info(f"  [WARN] {w}")

    # Tier 1: Qobuz (hi-fi FLAC -- priority, authenticated, reliable)
    if 1 not in skip_tiers and max_tier >= 1:
        logger.info("  [T1] Trying Qobuz...")
        _emit({"event": "phase", "stage": "acquire", "progress": 0.1, "note": "Trying T1 Qobuz..."})
        result = _try_tier1_qobuz(artist, title)
        attempts.append(result)
        if result.success:
            logger.info(f"  [OK] T1 SUCCESS ({result.elapsed:.1f}s)")
            _emit({"event": "phase", "stage": "stage", "progress": 0.8, "note": "Staging file..."})
            _emit({"event": "success", "path": result.path or "", "tier": "T1", "elapsed": time.perf_counter() - waterfall_start})
            _log_acquisition(artist, title, result)
            return result
        logger.info(f"  [--] T1: {result.error}")

    # Tier 2: Streamrip (alternative hi-fi fallback)
    if 2 not in skip_tiers and max_tier >= 2:
        logger.info("  [T2] Trying Streamrip...")
        _emit({"event": "phase", "stage": "acquire", "progress": 0.25, "note": "Trying T2 Streamrip..."})
        result = _try_tier2_streamrip(artist, title, album)
        attempts.append(result)
        if result.success:
            logger.info(f"  [OK] T2 SUCCESS ({result.elapsed:.1f}s)")
            _emit({"event": "phase", "stage": "stage", "progress": 0.8, "note": "Staging file..."})
            _emit({"event": "success", "path": result.path or "", "tier": "T2", "elapsed": time.perf_counter() - waterfall_start})
            _log_acquisition(artist, title, result)
            return result
        logger.info(f"  [--] T2: {result.error}")

    # Tier 3: Slskd (P2P FLAC)
    if 3 not in skip_tiers and max_tier >= 3:
        logger.info("  [T3] Trying Slskd...")
        _emit({"event": "phase", "stage": "acquire", "progress": 0.4, "note": "Trying T3 Slskd..."})
        result = _try_tier3_slskd(artist, title)
        attempts.append(result)
        if result.success:
            logger.info(f"  [OK] T3 SUCCESS ({result.elapsed:.1f}s)")
            _emit({"event": "phase", "stage": "stage", "progress": 0.8, "note": "Staging file..."})
            _emit({"event": "success", "path": result.path or "", "tier": "T3", "elapsed": time.perf_counter() - waterfall_start})
            _log_acquisition(artist, title, result)
            return result
        logger.info(f"  [--] T3: {result.error}")

    # Tier 4: Real-Debrid (Prowlarr + cached torrents)
    if 4 not in skip_tiers and max_tier >= 4:
        logger.info("  [T4] Trying Real-Debrid...")
        _emit({"event": "phase", "stage": "acquire", "progress": 0.55, "note": "Trying T4 Real-Debrid..."})
        result = _try_tier4_realdebrid(artist, title, album)
        attempts.append(result)
        if result.success:
            logger.info(f"  [OK] T4 SUCCESS ({result.elapsed:.1f}s)")
            _emit({"event": "phase", "stage": "stage", "progress": 0.8, "note": "Staging file..."})
            _emit({"event": "success", "path": result.path or "", "tier": "T4", "elapsed": time.perf_counter() - waterfall_start})
            _log_acquisition(artist, title, result)
            return result
        logger.info(f"  [--] T4: {result.error}")

    # Tier 5: SpotDL (YouTube 320k fallback)
    if 5 not in skip_tiers and max_tier >= 5:
        logger.info("  [T5] Trying SpotDL...")
        _emit({"event": "phase", "stage": "acquire", "progress": 0.7, "note": "Trying T5 SpotDL..."})
        result = _try_tier5_spotdl(artist, title, spotify_uri)
        attempts.append(result)
        if result.success:
            logger.info(f"  [OK] T5 SUCCESS ({result.elapsed:.1f}s)")
            _emit({"event": "phase", "stage": "stage", "progress": 0.8, "note": "Staging file..."})
            _emit({"event": "success", "path": result.path or "", "tier": "T5", "elapsed": time.perf_counter() - waterfall_start})
            _log_acquisition(artist, title, result)
            return result
        logger.info(f"  [--] T5: {result.error}")

    # All failed
    logger.warning(f"  [FAIL] All tiers failed for: {artist} - {title}")

    if attempts:
        last = attempts[-1]
        _emit({"event": "failure", "error": last.error or "Not found in any tier", "elapsed": time.perf_counter() - waterfall_start})
        return last

    _emit({"event": "failure", "error": "All acquisition tiers skipped or failed", "elapsed": time.perf_counter() - waterfall_start})
    return AcquisitionResult(
        success=False,
        tier=0,
        source="none",
        error="All acquisition tiers skipped or failed",
        artist=artist,
        title=title,
    )


def _log_acquisition(artist: str, title: str, result: AcquisitionResult) -> None:
    """Log successful acquisition to database."""
    if get_write_mode() != "apply_allowed":
        return

    try:
        conn = get_connection(timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE acquisition_queue
                SET status = 'completed', completed_at = datetime('now')
                WHERE artist = ? AND title = ? AND status = 'pending'
                """,
                (artist, title),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Failed to update acquisition log: %s", e)


def get_tier_status() -> Dict[str, Dict[str, Any]]:
    """Check availability of each acquisition tier."""
    from oracle.runtime_services import get_runtime_service_manifest

    services = get_runtime_service_manifest()
    return {
        "tier1_qobuz": {
            "available": _check_qobuz_available(),
            "description": "Qobuz hi-fi (FLAC up to 24-bit/96kHz)",
            "packaging_mode": services.get("qobuz", {}).get("packaging_mode"),
            "required_for_core_app": False,
        },
        "tier2_streamrip": {
            "available": _check_streamrip_available(),
            "description": "Streamrip hi-fi fallback",
            "packaging_mode": services.get("streamrip", {}).get("packaging_mode"),
            "required_for_core_app": False,
        },
        "tier3_slskd": {
            "available": _check_slskd_available(),
            "description": "Slskd peer-to-peer (FLAC)",
            "packaging_mode": services.get("slskd", {}).get("packaging_mode"),
            "required_for_core_app": False,
        },
        "tier4_realdebrid": {
            "available": _check_prowlarr_available() and _check_realdebrid_available(),
            "prowlarr": _check_prowlarr_available(),
            "realdebrid": _check_realdebrid_available(),
            "description": "Prowlarr + Real-Debrid (FLAC torrents)",
            "packaging_mode": "hybrid_optional_external",
            "required_for_core_app": False,
        },
        "tier5_spotdl": {
            "available": _check_spotdl_available(),
            "description": "SpotDL YouTube (320k MP3)",
            "packaging_mode": services.get("spotdl", {}).get("packaging_mode"),
            "required_for_core_app": False,
        },
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    # Subcommand dispatch: "acquire <artist> <title> [--album ALBUM] [--max-tier N]"
    if len(sys.argv) >= 2 and sys.argv[1] == "acquire":
        import argparse
        parser = argparse.ArgumentParser(prog="waterfall acquire")
        parser.add_argument("artist")
        parser.add_argument("title")
        parser.add_argument("--album", default=None)
        parser.add_argument("--max-tier", type=int, default=5)
        args = parser.parse_args(sys.argv[2:])
        acquire(args.artist, args.title, album=args.album, max_tier=args.max_tier)
        sys.exit(0)

    if len(sys.argv) < 3:
        print("\nLyra Acquisition Waterfall\n")
        print("Usage: python -m oracle.acquirers.waterfall <artist> <title> [album]")
        print("       python -m oracle.acquirers.waterfall acquire <artist> <title> [--album ALBUM]")
        print("\nTier status:")
        for tier, info in get_tier_status().items():
            avail = "[OK]" if info.get("available") else "[--]"
            desc = info.get("description", "")
            print(f"  {avail} {tier}: {desc}")
        sys.exit(0)

    artist = sys.argv[1]
    title = sys.argv[2]
    album = sys.argv[3] if len(sys.argv) > 3 else None

    result = acquire(artist, title, album)
    print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Tier: {result.tier}")
    print(f"  Source: {result.source}")
    if result.path:
        print(f"  Path: {result.path}")
    if result.error:
        print(f"  Error: {result.error}")
    print(f"  Elapsed: {result.elapsed:.1f}s")
