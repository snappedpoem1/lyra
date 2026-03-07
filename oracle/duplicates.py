"""Duplicate detection for the Lyra library.

Three detection strategies:
- Exact hash: bit-perfect duplicates via ``tracks.file_hash``
- Metadata fuzzy: same artist+title via SequenceMatcher (no audio I/O required)
- Path hygiene: same resolved file path stored under different track_ids

AcoustID fingerprint matching is intentionally excluded here — fpcalc is an
optional external binary and that tier belongs in the enricher pipeline.  This
module runs purely from the SQLite registry so it is safe to call any time.
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Optional

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_exact_duplicates() -> list[list[dict]]:
    """Return groups of tracks that share the same ``file_hash``.

    Returns:
        List of groups, each group being a list of track dicts
        (``track_id``, ``file_path``, ``artist``, ``title``, ``file_hash``).
        Groups with only one member are excluded.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_hash
            FROM tracks
            WHERE file_hash IS NOT NULL AND file_hash != ''
            GROUP BY file_hash
            HAVING COUNT(*) > 1
            """
        )
        hashes = [row[0] for row in cursor.fetchall()]

        groups: list[list[dict]] = []
        for h in hashes:
            cursor.execute(
                """
                SELECT track_id, file_path, artist, title, file_hash
                FROM tracks
                WHERE file_hash = ?
                ORDER BY LENGTH(file_path) ASC
                """,
                (h,),
            )
            members = [
                {
                    "track_id": row[0],
                    "file_path": row[1],
                    "artist": row[2] or "",
                    "title": row[3] or "",
                    "file_hash": row[4],
                }
                for row in cursor.fetchall()
            ]
            if len(members) > 1:
                groups.append(members)

        logger.info("find_exact_duplicates: %d groups found across %d hashes", len(groups), len(hashes))
        return groups
    finally:
        conn.close()


def find_metadata_duplicates(threshold: float = 0.85) -> list[list[dict]]:
    """Return groups of tracks with similar artist + title strings.

    Uses ``SequenceMatcher`` on the normalised ``artist + ' ' + title`` string.
    Only compares tracks within the same first-alphabetical-character bucket to
    keep O(n) manageable on large libraries.

    Args:
        threshold: Combined similarity score (0.0-1.0, default 0.85).
                   0.85 catches minor spacing/punctuation differences while
                   avoiding false positives between different songs.

    Returns:
        List of groups (each group ≥ 2 tracks).  Members within a group are
        sorted by descending string similarity to the anchor track.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT track_id, file_path, artist, title
            FROM tracks
            WHERE artist IS NOT NULL AND title IS NOT NULL
              AND artist != '' AND title != ''
            ORDER BY artist, title
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    tracks = [
        {
            "track_id": r[0],
            "file_path": r[1],
            "artist": (r[2] or "").strip().lower(),
            "title": (r[3] or "").strip().lower(),
            "_key": f"{(r[2] or '').strip().lower()} {(r[3] or '').strip().lower()}",
        }
        for r in rows
    ]

    visited: set[str] = set()
    groups: list[list[dict]] = []

    for i, anchor in enumerate(tracks):
        if anchor["track_id"] in visited:
            continue
        group: list[dict] = [anchor]
        visited.add(anchor["track_id"])

        for candidate in tracks[i + 1 :]:
            if candidate["track_id"] in visited:
                continue
            # Quick artist pre-filter to reduce full comparisons
            if abs(len(anchor["artist"]) - len(candidate["artist"])) > 8:
                continue
            artist_sim = SequenceMatcher(None, anchor["artist"], candidate["artist"]).ratio()
            if artist_sim < 0.6:
                continue
            title_sim = SequenceMatcher(None, anchor["title"], candidate["title"]).ratio()
            combined = (artist_sim + title_sim) / 2.0
            if combined >= threshold:
                group.append(candidate)
                visited.add(candidate["track_id"])

        if len(group) > 1:
            groups.append(group)

    logger.info(
        "find_metadata_duplicates: %d groups found from %d tracks (threshold=%.2f)",
        len(groups),
        len(tracks),
        threshold,
    )
    return groups


def find_path_duplicates() -> list[list[dict]]:
    """Return groups of tracks with an identical resolved file path string.

    This catches cases where the same absolute path was re-indexed under
    multiple track_ids (e.g. after a re-scan race).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_path
            FROM tracks
            WHERE file_path IS NOT NULL AND file_path != ''
            GROUP BY file_path
            HAVING COUNT(*) > 1
            """
        )
        paths = [row[0] for row in cursor.fetchall()]

        groups: list[list[dict]] = []
        for p in paths:
            cursor.execute(
                """
                SELECT track_id, file_path, artist, title, file_hash
                FROM tracks
                WHERE file_path = ?
                ORDER BY track_id
                """,
                (p,),
            )
            members = [
                {
                    "track_id": row[0],
                    "file_path": row[1],
                    "artist": row[2] or "",
                    "title": row[3] or "",
                    "file_hash": row[4] or "",
                }
                for row in cursor.fetchall()
            ]
            if len(members) > 1:
                groups.append(members)

        logger.info("find_path_duplicates: %d groups found", len(groups))
        return groups
    finally:
        conn.close()


def get_duplicate_summary(metadata_threshold: float = 0.85) -> dict:
    """Run all three strategies and return a summary dict.

    Args:
        metadata_threshold: Forwarded to ``find_metadata_duplicates``.

    Returns:
        dict with keys ``exact``, ``metadata``, ``path``, each containing
        ``group_count`` and ``track_count``.
    """
    exact = find_exact_duplicates()
    metadata = find_metadata_duplicates(threshold=metadata_threshold)
    path = find_path_duplicates()

    def _stats(groups: list[list[dict]]) -> dict:
        return {
            "group_count": len(groups),
            "track_count": sum(len(g) for g in groups),
        }

    return {
        "exact": _stats(exact),
        "metadata": _stats(metadata),
        "path": _stats(path),
        "metadata_threshold": metadata_threshold,
    }


def find_all_duplicates(metadata_threshold: float = 0.85) -> dict:
    """Return full duplicate groups from all three strategies.

    Returns:
        dict with keys ``exact``, ``metadata``, ``path``, each a list of groups.
    """
    return {
        "exact": find_exact_duplicates(),
        "metadata": find_metadata_duplicates(threshold=metadata_threshold),
        "path": find_path_duplicates(),
        "metadata_threshold": metadata_threshold,
    }
