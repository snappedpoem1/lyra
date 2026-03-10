"""MBID Identity Spine — Wave 10 (SPEC-010)

Batch-resolves MusicBrainz IDs for all active tracks that are currently
missing ``recording_mbid``.  Uses the existing rate-limited ``enrich_by_text``
helper in ``oracle.enrichers.musicbrainz`` and writes results directly back to
the ``tracks`` table.

Why this module exists
-----------------------
- 2,455 active tracks; <5 had a ``recording_mbid`` before Wave 10.
- Without MBIDs, ``CreditMapper.map_batch`` has nothing to look up and
  ``track_credits`` stays empty.
- Record ``last_enriched_at`` even on no-match so we skip those tracks on
  future runs rather than hammering MB repeatedly.

CLI
---
::

    oracle mbid resolve [--limit N] [--min-confidence F] [--all]
    oracle mbid stats
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from oracle.db.schema import get_connection
from oracle.enrichers.musicbrainz import enrich_by_text

if TYPE_CHECKING:
    from oracle.enrichers.musicbrainz import RecordingMatch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ResolveResult:
    """Summary of a ``resolve_batch`` run."""

    total_eligible: int = 0
    resolved: int = 0
    skipped: int = 0
    no_match: int = 0
    failed: int = 0


@dataclass
class MBIDStats:
    """Library-wide MBID coverage snapshot."""

    total_active: int = 0
    recording_mbid_count: int = 0
    artist_mbid_count: int = 0
    release_group_mbid_count: int = 0
    isrc_count: int = 0
    coverage_pct: float = 0.0


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class MBIdentityResolver:
    """Batch-resolve MusicBrainz IDs for tracks missing them.

    Uses ``enrich_by_text`` (fuzzy text search, 1.1 s/req rate limit) as
    the primary resolution path.  MBID-based enrichment is skipped here —
    this module is specifically the *bootstrap* that populates the columns
    from scratch.
    """

    # Columns written on every successful (or no-match) resolve attempt
    _WRITE_COLS = (
        "recording_mbid",
        "artist_mbid",
        "release_mbid",
        "release_group_mbid",
        "isrc",
        "last_enriched_at",
    )

    def resolve_batch(
        self,
        limit: int = 100,
        min_confidence: float = 0.65,
        only_missing: bool = True,
    ) -> ResolveResult:
        """Resolve a batch of tracks via MusicBrainz text search.

        Args:
            limit: Maximum number of tracks to process per call.
            min_confidence: Minimum ``RecordingMatch.confidence`` to accept.
            only_missing: When ``True`` (default), skip tracks that already
                have a non-empty ``recording_mbid``.

        Returns:
            :class:`ResolveResult` with per-category counters.
        """
        conn = get_connection()
        c = conn.cursor()

        if only_missing:
            c.execute(
                """SELECT t.track_id, t.artist, t.title, t.album, t.duration
                   FROM tracks t
                   WHERE t.status = 'active'
                     AND (t.recording_mbid IS NULL OR t.recording_mbid = '')
                   ORDER BY t.last_seen_at DESC NULLS LAST
                   LIMIT ?""",
                (limit,),
            )
        else:
            c.execute(
                """SELECT t.track_id, t.artist, t.title, t.album, t.duration
                   FROM tracks t
                   WHERE t.status = 'active'
                   ORDER BY t.last_seen_at DESC NULLS LAST
                   LIMIT ?""",
                (limit,),
            )

        rows = c.fetchall()
        conn.close()

        result = ResolveResult(total_eligible=len(rows))

        for track_id, artist, title, album, duration in rows:
            try:
                match = enrich_by_text(
                    artist=artist or "",
                    title=title or "",
                    album=album,
                    duration=duration,
                    min_similarity=0.55,  # looser than the default — scoring handles confidence
                )
            except Exception as exc:
                logger.warning(
                    "MBIdentityResolver: track=%s error during enrich_by_text: %s",
                    track_id, exc,
                )
                result.failed += 1
                # Still stamp last_enriched_at so we don't retry immediately
                self._stamp_enriched(track_id)
                continue

            if match is None or match.confidence < min_confidence:
                logger.debug(
                    "MBIdentityResolver: no match track=%s artist=%r title=%r (confidence=%.3f)",
                    track_id, artist, title, match.confidence if match else 0.0,
                )
                result.no_match += 1
                self._stamp_enriched(track_id)
                continue

            # --- Write MBID columns ---
            self._write_match(track_id, match)
            result.resolved += 1

            logger.info(
                "MBIdentityResolver: resolved track=%s → recording_mbid=%s confidence=%.3f",
                track_id, match.recording_mbid, match.confidence,
            )

        logger.info(
            "MBIdentityResolver.resolve_batch: eligible=%d resolved=%d no_match=%d failed=%d",
            result.total_eligible, result.resolved, result.no_match, result.failed,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_match(self, track_id: str, match: RecordingMatch) -> None:
        """Persist MBID columns for a successfully resolved track."""
        conn = get_connection()
        c = conn.cursor()
        now = time.time()
        c.execute(
            """UPDATE tracks
               SET recording_mbid      = ?,
                   artist_mbid         = ?,
                   release_mbid        = ?,
                   release_group_mbid  = ?,
                   isrc                = ?,
                   last_enriched_at    = ?
               WHERE track_id = ?""",
            (
                match.recording_mbid,
                match.artist_mbid,
                getattr(match, "release_mbid", None),
                getattr(match, "release_group_mbid", None),
                match.isrc,
                now,
                track_id,
            ),
        )
        conn.commit()
        conn.close()

    def _stamp_enriched(self, track_id: str) -> None:
        """Write ``last_enriched_at`` without touching MBID columns."""
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE tracks SET last_enriched_at = ? WHERE track_id = ?",
            (time.time(), track_id),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> MBIDStats:
        """Return library-wide MBID coverage counts.

        Returns:
            :class:`MBIDStats` with record counts and coverage percentage.
        """
        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM tracks WHERE status = 'active'")
        total_active = c.fetchone()[0]

        def _count(col: str) -> int:
            c.execute(
                f"SELECT COUNT(*) FROM tracks WHERE status = 'active' AND {col} IS NOT NULL AND {col} != ''",  # noqa: S608
            )
            return c.fetchone()[0]

        recording_count = _count("recording_mbid")
        artist_count = _count("artist_mbid")
        rg_count = _count("release_group_mbid")
        isrc_count = _count("isrc")

        conn.close()

        coverage = (recording_count / total_active * 100) if total_active else 0.0
        return MBIDStats(
            total_active=total_active,
            recording_mbid_count=recording_count,
            artist_mbid_count=artist_count,
            release_group_mbid_count=rg_count,
            isrc_count=isrc_count,
            coverage_pct=round(coverage, 1),
        )
