"""Credit Attribution — F-003

Extracts production/composition credits from MusicBrainz recording relationships
and stores them in the ``track_credits`` table.

Data sources:
    - MusicBrainz recording relationships (inc=recording-rels+artist-credits+work-rels)
    - Artist-credit join-phrases (feat., ft., x) from MB artist-credit list

Role normalisation:
    MB relationship type → canonical role stored in track_credits.role
    "producer"  → producer
    "mix"       → mixer
    "mastering" → mastering
    "remixer"   → remixer
    "composer"  → composer
    "lyricist"  → lyricist
    "arranger"  → arranger
    "instrument"→ performer:{instrument}
    "vocal"     → vocals
    "recording" → engineer
    "featured"  → featured          (from artist-credit join-phrase)

Usage::

    # Single track by MBID
    from oracle.enrichers.credit_mapper import CreditMapper
    cm = CreditMapper()
    credits = cm.map_from_mbid("track-db-id", "mb-recording-uuid")

    # Auto-map batch (uses tracks.musicbrainz_id where present)
    result = cm.map_batch(limit=200)

    # Read back
    credits = cm.get_credits_for_track("track-db-id")

Author: Lyra Oracle — Sprint 2, F-003
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from oracle.db.schema import get_connection
from oracle.enrichers.musicbrainz import (
    _base,
    _request,
    search_recording,
)

logger = logging.getLogger(__name__)

# ─── Role mapping ─────────────────────────────────────────────────────────────

_RELATION_ROLE_MAP: Dict[str, str] = {
    "producer": "producer",
    "mix": "mixer",
    "mastering": "mastering",
    "remixer": "remixer",
    "composer": "composer",
    "lyricist": "lyricist",
    "arranger": "arranger",
    "recording": "engineer",
    "editor": "editor",
    "vocal": "vocals",
    "concertmaster": "performer",
    "instrument": "performer",
    "instrument arranger": "arranger",
    "additional": "additional",
    "programming": "programmer",
    "orchestra": "performer",
    "conductor": "conductor",
    "chorus master": "conductor",
    "sound": "engineer",
}

# Joinphrases that indicate a featured artist
_FEAT_JOINPHRASES = {"feat.", "ft.", "feat", "ft", "x", "w/", "and", "&"}


# ─── MB fetch with rels ───────────────────────────────────────────────────────

def _get_recording_with_relations(mbid: str) -> Dict[str, Any]:
    """Fetch a MB recording including all relationship types and work relations.

    Uses a separate ``inc`` set to ``recording-rels`` that the core
    ``get_recording_details`` does not request.
    """
    params = {
        "inc": "artist-credits+recording-rels+work-rels+work-level-rels",
    }
    return _request(f"{_base()}/recording/{mbid}", params)


# ─── Main class ───────────────────────────────────────────────────────────────

class CreditMapper:
    """Extract and persist track credits from MusicBrainz relationships."""

    def map_from_mbid(
        self,
        track_id: str,
        recording_mbid: str,
    ) -> List[Dict[str, Any]]:
        """Map credits for a track that has a known MusicBrainz recording ID.

        Fetches recording relations from MB, parses credits, upserts to the
        ``track_credits`` table, and returns the parsed credit list.

        Args:
            track_id: Internal lyra_registry track ID.
            recording_mbid: MusicBrainz recording UUID.

        Returns:
            List of credit dicts: {artist_name, artist_id, role, credited_as,
            connection_type}.
        """
        data = _get_recording_with_relations(recording_mbid)
        if not data or "error" in data:
            logger.warning("CreditMapper: MB returned no data for mbid=%s", recording_mbid)
            return []

        credits: List[Dict[str, Any]] = []

        # 1. Extract featured artists from artist-credit list
        artist_credit = data.get("artist-credit", [])
        for i, credit in enumerate(artist_credit):
            if i == 0:
                # Primary artist — skip, they're the main performer
                continue
            a = credit.get("artist", {})
            artist_name = credit.get("name") or a.get("name", "")
            artist_mbid = a.get("id", "")
            # Treat secondary credits with "feat." joinphrase as "featured"
            prev_joinphrase = (artist_credit[i - 1].get("joinphrase", "") or "").lower().strip().rstrip(".")
            if prev_joinphrase in _FEAT_JOINPHRASES or artist_name:
                credits.append({
                    "artist_name": artist_name,
                    "artist_id": artist_mbid,
                    "role": "featured",
                    "credited_as": credit.get("name") or artist_name,
                    "connection_type": "mb_artist_credit",
                })

        # 2. Parse direct recording relationships
        for rel in data.get("relations", []):
            rel_type = (rel.get("type") or "").lower()
            role = _RELATION_ROLE_MAP.get(rel_type)
            if not role:
                # Try contains-match for compound types like "instrument: ..."
                for key, mapped in _RELATION_ROLE_MAP.items():
                    if key in rel_type:
                        role = mapped
                        break
            if not role:
                # Keep unknown but important relations generically
                role = rel_type.replace(" ", "_") if rel_type else "other"

            # Enrich performer roles with instrument attribute
            if role == "performer" and rel.get("attributes"):
                instrument = ", ".join(a for a in rel.get("attributes", []) if a)
                if instrument:
                    role = f"performer:{instrument}"

            # Artist entity
            artist_entity = rel.get("artist") or {}
            artist_name = artist_entity.get("name", "")
            artist_mbid = artist_entity.get("id", "")

            if not artist_name:
                continue

            credits.append({
                "artist_name": artist_name,
                "artist_id": artist_mbid,
                "role": role,
                "credited_as": artist_entity.get("sort-name") or artist_name,
                "connection_type": "mb_relation",
            })

        # 3. Walk work relations for composer/lyricist (one level deep)
        for work_rel in data.get("relations", []):
            if work_rel.get("target-type") != "work":
                continue
            work = work_rel.get("work", {})
            for wr in work.get("relations", []):
                wr_type = (wr.get("type") or "").lower()
                w_role = _RELATION_ROLE_MAP.get(wr_type, wr_type)
                a = wr.get("artist", {})
                artist_name = a.get("name", "")
                if not artist_name:
                    continue
                credits.append({
                    "artist_name": artist_name,
                    "artist_id": a.get("id", ""),
                    "role": w_role,
                    "credited_as": a.get("sort-name") or artist_name,
                    "connection_type": "mb_work_rel",
                })

        if credits:
            self._persist(track_id, credits)

        logger.info(
            "CreditMapper: track=%s mbid=%s → %d credits",
            track_id, recording_mbid, len(credits),
        )
        return credits

    def map_from_search(
        self,
        track_id: str,
        artist: str,
        title: str,
        album: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Fuzzy-search MB for a recording, then map credits if found.

        Falls back gracefully — if no MBID is found, returns an empty list
        without raising.

        Args:
            track_id: Internal lyra_registry track ID.
            artist: Track artist name.
            title: Track title.
            album: Optional album name for disambiguation.
            duration: Optional duration in seconds.

        Returns:
            List of credit dicts, or [] if MB lookup failed.
        """
        data = search_recording(artist, title, album=album, duration=duration, limit=3)
        recordings = data.get("recordings", [])
        if not recordings:
            logger.debug("CreditMapper: no MB results for %s - %s", artist, title)
            return []

        best = recordings[0]
        mbid = best.get("id")
        if not mbid:
            return []

        return self.map_from_mbid(track_id, mbid)

    def map_batch(
        self,
        limit: int = 500,
        only_missing: bool = True,
    ) -> Dict[str, Any]:
        """Map credits for a batch of tracks that have a musicbrainz_id stored.

        Args:
            limit: Max tracks to process.
            only_missing: If True, skip tracks that already have rows in
                ``track_credits``.

        Returns:
            Dict with processed, skipped, failed, total_eligible counts.
        """
        conn = get_connection()
        c = conn.cursor()

        if only_missing:
            c.execute(
                """SELECT t.track_id, t.musicbrainz_id, t.artist, t.title
                   FROM tracks t
                   WHERE t.musicbrainz_id IS NOT NULL
                     AND t.musicbrainz_id != ''
                     AND NOT EXISTS (
                         SELECT 1 FROM track_credits tc WHERE tc.track_id = t.track_id
                     )
                   LIMIT ?""",
                (limit,),
            )
        else:
            c.execute(
                """SELECT track_id, musicbrainz_id, artist, title
                   FROM tracks
                   WHERE musicbrainz_id IS NOT NULL
                     AND musicbrainz_id != ''
                   LIMIT ?""",
                (limit,),
            )

        rows = c.fetchall()
        conn.close()

        total_eligible = len(rows)
        processed = 0
        skipped = 0
        failed = 0

        for row in rows:
            track_id, mbid, artist, title = row
            try:
                credits = self.map_from_mbid(track_id, mbid)
                if credits:
                    processed += 1
                else:
                    skipped += 1
                # Respect MB rate limit — _request already handles this, but
                # add a small buffer between batch rows to be safe.
                time.sleep(0.1)
            except Exception as exc:
                logger.warning("CreditMapper.map_batch: track=%s error=%s", track_id, exc)
                failed += 1

        return {
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
            "total_eligible": total_eligible,
        }

    def get_credits_for_track(self, track_id: str) -> List[Dict[str, Any]]:
        """Return all credits stored for a track, grouped by role.

        Args:
            track_id: Internal lyra_registry track ID.

        Returns:
            List of dicts: {artist_name, artist_id, role, credited_as,
            connection_type, id}.
        """
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            """SELECT id, artist_name, artist_id, role, credited_as, connection_type
               FROM track_credits
               WHERE track_id = ?
               ORDER BY role, artist_name""",
            (track_id,),
        )
        rows = c.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "artist_name": r[1],
                "artist_id": r[2],
                "role": r[3],
                "credited_as": r[4],
                "connection_type": r[5],
            }
            for r in rows
        ]

    def get_credits_summary(
        self,
        limit_artists: int = 20,
    ) -> Dict[str, Any]:
        """Library-wide credit statistics.

        Returns:
            Dict with total_credits, top_producers, top_composers,
            top_featured, roles_breakdown.
        """
        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM track_credits")
        total = c.fetchone()[0]

        def _top_by_role(role: str, n: int = 10) -> List[Dict[str, Any]]:
            c.execute(
                """SELECT artist_name, COUNT(*) as cnt
                   FROM track_credits
                   WHERE role = ?
                   GROUP BY artist_name
                   ORDER BY cnt DESC
                   LIMIT ?""",
                (role, n),
            )
            return [{"name": r[0], "count": r[1]} for r in c.fetchall()]

        c.execute(
            """SELECT role, COUNT(*) as cnt
               FROM track_credits
               GROUP BY role
               ORDER BY cnt DESC""",
        )
        roles = {r[0]: r[1] for r in c.fetchall()}

        conn.close()
        return {
            "total_credits": total,
            "top_producers": _top_by_role("producer"),
            "top_composers": _top_by_role("composer"),
            "top_featured": _top_by_role("featured"),
            "roles_breakdown": roles,
        }

    def map_batch_search(
        self,
        limit: int = 30,
        rate_limit_s: float = 1.1,
    ) -> Dict[str, Any]:
        """Map credits for tracks without existing credit rows using MB search.

        Suitable as a background job — works even when recording_mbid is NULL
        by performing artist+title searches against MusicBrainz.

        Rate-limits to ~1 request/second to respect MB policy.

        Args:
            limit: Max tracks to process per call.
            rate_limit_s: Seconds to wait between MB requests.

        Returns:
            Dict with processed, found, empty, failed, skipped counts.
        """
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT t.track_id, t.artist, t.title, t.album, t.duration
            FROM tracks t
            WHERE t.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM track_credits tc WHERE tc.track_id = t.track_id
              )
            ORDER BY t.created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = c.fetchall()
        conn.close()

        processed = found = empty = failed = 0
        for row in rows:
            track_id, artist, title, album, duration = row
            try:
                credits = self.map_from_search(
                    track_id, artist or "", title or "",
                    album=album, duration=duration,
                )
                processed += 1
                if credits:
                    found += 1
                else:
                    empty += 1
            except Exception as exc:
                logger.warning("CreditMapper.map_batch_search: %s - %s failed: %s", artist, title, exc)
                failed += 1
            time.sleep(rate_limit_s)

        return {"processed": processed, "found": found, "empty": empty, "failed": failed}

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _persist(
        self,
        track_id: str,
        credits: List[Dict[str, Any]],
    ) -> None:
        """Upsert credits into track_credits, avoiding duplicates.

        Uses (track_id, artist_name, role) as the natural key.
        """
        conn = get_connection()
        c = conn.cursor()
        for credit in credits:
            # Check if this (track_id, artist_name, role) already exists
            c.execute(
                """SELECT id FROM track_credits
                   WHERE track_id = ? AND artist_name = ? AND role = ?""",
                (track_id, credit["artist_name"], credit["role"]),
            )
            existing = c.fetchone()
            if existing:
                continue
            c.execute(
                """INSERT INTO track_credits
                       (track_id, artist_id, artist_name, role, credited_as, connection_type)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    track_id,
                    credit.get("artist_id", ""),
                    credit["artist_name"],
                    credit["role"],
                    credit.get("credited_as", credit["artist_name"]),
                    credit.get("connection_type", "unknown"),
                ),
            )
        conn.commit()
        conn.close()


# ─── Module-level convenience ────────────────────────────────────────────────

def map_credits_for_track(
    track_id: str,
    recording_mbid: Optional[str] = None,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    album: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convenience wrapper — map credits for a single track.

    Prefers MBID lookup; falls back to search if mbid not provided.
    """
    cm = CreditMapper()
    if recording_mbid:
        return cm.map_from_mbid(track_id, recording_mbid)
    if artist and title:
        return cm.map_from_search(track_id, artist, title, album=album)
    logger.warning("map_credits_for_track: need either recording_mbid or artist+title")
    return []
