"""Smart Acquisition Pipeline - quality-controlled music acquisition."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from oracle.config import LIBRARY_BASE, get_connection, guard_bypass_allowed, guard_bypass_reason

logger = logging.getLogger(__name__)

CANONICAL_QUEUE_COMPLETE_STATUS = "completed"


@dataclass
class AcquisitionRequest:
    """A request to acquire a track."""

    artist: str
    title: str
    album: Optional[str] = None
    year: Optional[int] = None
    isrc: Optional[str] = None
    spotify_uri: Optional[str] = None
    source: str = "manual"
    priority: float = 5.0


@dataclass
class AcquisitionResult:
    """Result of an acquisition attempt."""

    success: bool
    request: AcquisitionRequest
    filepath: Optional[Path] = None
    canonical_artist: Optional[str] = None
    canonical_title: Optional[str] = None
    canonical_album: Optional[str] = None
    genres: List[str] = None
    quality: str = "unknown"
    rejection_reason: Optional[str] = None
    tier_used: int = 0
    elapsed: float = 0.0

    def __post_init__(self) -> None:
        if self.genres is None:
            self.genres = []


class SmartAcquisition:
    """Quality-controlled acquisition pipeline."""

    def __init__(
        self,
        library_path: Path,
        min_confidence: float = 0.7,
        allow_duplicates: bool = False,
        require_validation: bool = True,
        skip_guard: bool = False,
    ) -> None:
        self.library_path = Path(library_path)
        self.min_confidence = min_confidence
        self.allow_duplicates = allow_duplicates
        self.require_validation = require_validation
        self.skip_guard = skip_guard and guard_bypass_allowed()

        self._validator = None
        self._db = None
        self.last_queue_summary: Dict[str, int] = {}

        if skip_guard and not self.skip_guard:
            logger.error(
                "[smart_pipeline] Guard bypass requested but LYRA_ALLOW_GUARD_BYPASS is not enabled."
            )
        if self.skip_guard:
            logger.warning(
                "[smart_pipeline] Guard bypass enabled (reason=%s).",
                guard_bypass_reason(),
            )

    @property
    def validator(self):
        if self._validator is None:
            from oracle.acquirers.validator import validate_track

            self._validator = validate_track
        return self._validator

    @property
    def db(self):
        if self._db is None:
            self._db = get_connection(timeout=10.0)
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def _normalize_queue_statuses(self) -> int:
        """Normalize legacy queue statuses to canonical values."""
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE acquisition_queue SET status = ? WHERE lower(status) = 'complete'",
            (CANONICAL_QUEUE_COMPLETE_STATUS,),
        )
        return cursor.rowcount

    def _check_duplicate(self, artist: str, title: str) -> Optional[str]:
        """Check if track already exists in library."""
        cursor = self.db.cursor()

        artist_norm = artist.lower().strip()
        title_norm = re.sub(r"\s*[\(\[].*?[\)\]]", "", title.lower()).strip()

        cursor.execute(
            """
            SELECT artist, title, filepath
            FROM tracks
            WHERE status = 'active'
            """
        )

        for db_artist, db_title, filepath in cursor.fetchall():
            db_artist_norm = (db_artist or "").lower().strip()
            db_title_norm = re.sub(r"\s*[\(\[].*?[\)\]]", "", (db_title or "").lower()).strip()

            from difflib import SequenceMatcher

            artist_sim = SequenceMatcher(None, artist_norm, db_artist_norm).ratio()
            title_sim = SequenceMatcher(None, title_norm, db_title_norm).ratio()

            if artist_sim > 0.85 and title_sim > 0.85:
                return filepath

        return None

    def _infer_quality(self, filepath: Path) -> str:
        """Infer audio quality from file."""
        ext = filepath.suffix.lower()

        if ext in {".flac", ".wav", ".aiff", ".alac"}:
            return "flac"

        try:
            import mutagen

            audio = mutagen.File(str(filepath))
            if audio and hasattr(audio.info, "bitrate"):
                bitrate = audio.info.bitrate / 1000
                if bitrate >= 300:
                    return "320k"
                if bitrate >= 200:
                    return "256k"
                return "<256k"
        except Exception as exc:
            logger.debug("[smart_pipeline] bitrate probe failed for %s: %s", filepath, exc)

        if ext == ".mp3":
            return "320k"

        return "unknown"

    def _sanitize_filename(self, artist: str, title: str, ext: str = ".flac") -> str:
        clean = f"{artist} - {title}"
        clean = re.sub(r"[<>:\"/\\|?*]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = clean[:200]
        return f"{clean}{ext}"

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        """Acquire a track with validation + waterfall + post-processing."""
        start = time.perf_counter()
        logger.info("Acquiring: %s - %s", request.artist, request.title)

        if self.require_validation:
            logger.info("  [1/4] Validating metadata...")
            validation = self.validator(request.artist, request.title)

            if not validation.valid:
                return AcquisitionResult(
                    success=False,
                    request=request,
                    rejection_reason=validation.rejection_reason or "Failed validation",
                    elapsed=time.perf_counter() - start,
                )

            if validation.confidence < self.min_confidence:
                return AcquisitionResult(
                    success=False,
                    request=request,
                    rejection_reason=f"Low confidence: {validation.confidence:.2f}",
                    elapsed=time.perf_counter() - start,
                )

            canonical_artist = validation.canonical_artist or request.artist
            canonical_title = validation.canonical_title or request.title
            canonical_album = validation.canonical_album or request.album
            genres = validation.genres or []
        else:
            canonical_artist = request.artist
            canonical_title = request.title
            canonical_album = request.album
            genres = []

        if not self.allow_duplicates:
            logger.info("  [2/4] Checking for duplicates...")
            existing = self._check_duplicate(canonical_artist, canonical_title)
            if existing:
                return AcquisitionResult(
                    success=False,
                    request=request,
                    rejection_reason=f"Duplicate exists: {existing}",
                    elapsed=time.perf_counter() - start,
                )

        logger.info("  [3/4] Acquiring audio...")
        from oracle.acquirers.waterfall import acquire as waterfall_acquire

        waterfall_result = waterfall_acquire(
            artist=canonical_artist,
            title=canonical_title,
            album=canonical_album,
            spotify_uri=request.spotify_uri,
            skip_guard=self.skip_guard,
            pre_validated=self.require_validation,
        )

        if not waterfall_result.success:
            return AcquisitionResult(
                success=False,
                request=request,
                rejection_reason=waterfall_result.error or "Waterfall failed",
                tier_used=waterfall_result.tier,
                elapsed=time.perf_counter() - start,
            )

        acquired_path = Path(waterfall_result.path or "")
        if not acquired_path.exists():
            return AcquisitionResult(
                success=False,
                request=request,
                rejection_reason=f"Downloaded file missing: {acquired_path}",
                tier_used=waterfall_result.tier,
                elapsed=time.perf_counter() - start,
            )

        logger.info("  [4/4] Post-processing...")
        quality = self._infer_quality(acquired_path)

        ext = acquired_path.suffix
        clean_filename = self._sanitize_filename(canonical_artist, canonical_title, ext)
        final_path = self.library_path / clean_filename

        counter = 1
        while final_path.exists():
            final_path = self.library_path / f"{final_path.stem} ({counter}){ext}"
            counter += 1

        import shutil

        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(acquired_path), str(final_path))

        logger.info("  Success: %s", final_path.name)
        return AcquisitionResult(
            success=True,
            request=request,
            filepath=final_path,
            canonical_artist=canonical_artist,
            canonical_title=canonical_title,
            canonical_album=canonical_album,
            genres=genres,
            quality=quality,
            tier_used=waterfall_result.tier,
            elapsed=time.perf_counter() - start,
        )

    def acquire_batch(self, requests: List[AcquisitionRequest], max_failures: int = 5) -> List[AcquisitionResult]:
        """Acquire multiple tracks with failure threshold."""
        results: List[AcquisitionResult] = []
        failures = 0

        for i, request in enumerate(requests):
            logger.info("[%s/%s] Processing request", i + 1, len(requests))
            result = self.acquire(request)
            results.append(result)

            if not result.success:
                failures += 1
                if failures >= max_failures:
                    logger.warning("Stopping batch after %s consecutive failures.", failures)
                    break
            else:
                failures = 0

            time.sleep(1.0)

        return results

    def process_queue(self, limit: int = 50, max_retries: int = 3) -> List[AcquisitionResult]:
        """Process pending items from acquisition_queue and emit telemetry summary."""
        cursor = self.db.cursor()
        normalized = self._normalize_queue_statuses()
        if normalized:
            logger.info("[queue] Normalized %s legacy 'complete' status rows.", normalized)

        cursor.execute(
            """
            SELECT id, artist, title, album, spotify_uri,
                   COALESCE(priority_score, 0) AS priority_score,
                   COALESCE(retry_count, 0) AS retry_count
            FROM acquisition_queue
            WHERE status = 'pending'
            ORDER BY priority_score DESC, datetime(added_at) ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        )

        rows = cursor.fetchall()
        if not rows:
            logger.info("No pending items in queue.")
            self.last_queue_summary = {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "retried": 0,
                "rejected": 0,
            }
            return []

        requests = [
            AcquisitionRequest(
                artist=row[1],
                title=row[2],
                album=row[3],
                spotify_uri=row[4],
                priority=float(row[5] or 0),
                source="queue",
            )
            for row in rows
        ]

        results = self.acquire_batch(requests)

        succeeded = 0
        failed = 0
        retried = 0
        rejected = 0

        for row, result in zip(rows, results):
            queue_id = row[0]
            retry_count = int(row[6] or 0)
            if result.success:
                succeeded += 1
                cursor.execute(
                    """
                    UPDATE acquisition_queue
                    SET status = ?, completed_at = datetime('now'), error = NULL
                    WHERE id = ?
                    """,
                    (CANONICAL_QUEUE_COMPLETE_STATUS, queue_id),
                )
                continue

            failed += 1
            new_retry_count = retry_count + 1
            new_status = "failed" if new_retry_count >= max_retries else "pending"
            if new_status == "pending":
                retried += 1
            else:
                rejected += 1

            cursor.execute(
                """
                UPDATE acquisition_queue
                SET status = ?, error = ?, retry_count = ?
                WHERE id = ?
                """,
                (new_status, (result.rejection_reason or "Acquisition failed"), new_retry_count, queue_id),
            )

        self.db.commit()

        self.last_queue_summary = {
            "processed": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "retried": retried,
            "rejected": rejected,
        }
        logger.info(
            "[queue] processed=%s succeeded=%s failed=%s retried=%s rejected=%s",
            self.last_queue_summary["processed"],
            self.last_queue_summary["succeeded"],
            self.last_queue_summary["failed"],
            self.last_queue_summary["retried"],
            self.last_queue_summary["rejected"],
        )
        return results


def main() -> None:
    """CLI interface for smart acquisition."""
    import argparse

    parser = argparse.ArgumentParser(description="Smart music acquisition")
    parser.add_argument("--artist", help="Artist name")
    parser.add_argument("--title", help="Track title")
    parser.add_argument("--album", help="Album name (optional)")
    parser.add_argument("--queue", action="store_true", help="Process queue")
    parser.add_argument("--limit", type=int, default=10, help="Queue limit")
    parser.add_argument("--library", default=str(LIBRARY_BASE))
    parser.add_argument("--no-validate", action="store_true", help="Skip validation")
    parser.add_argument(
        "--skip-guard",
        action="store_true",
        help="Skip guard checks (requires LYRA_ALLOW_GUARD_BYPASS=1)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    pipeline = SmartAcquisition(
        library_path=Path(args.library),
        require_validation=not args.no_validate,
        skip_guard=args.skip_guard,
    )

    try:
        if args.queue:
            results = pipeline.process_queue(limit=args.limit)
            print(f"\n=== Processed {len(results)} items ===")
            summary = pipeline.last_queue_summary
            print(
                "Summary: "
                f"succeeded={summary.get('succeeded', 0)} "
                f"failed={summary.get('failed', 0)} "
                f"retried={summary.get('retried', 0)} "
                f"rejected={summary.get('rejected', 0)}"
            )
            return

        if args.artist and args.title:
            request = AcquisitionRequest(artist=args.artist, title=args.title, album=args.album)
            result = pipeline.acquire(request)
            if result.success:
                print(f"\nAcquired: {result.filepath}")
                print(f"Artist: {result.canonical_artist}")
                print(f"Title: {result.canonical_title}")
                print(f"Quality: {result.quality}")
                print(f"Tier: {result.tier_used}")
            else:
                print(f"\nFailed: {result.rejection_reason}")
            return

        parser.print_help()
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
