"""Unified metadata enrichment pipeline."""

from __future__ import annotations

from typing import Dict, List, Optional
import json
import logging
import time

from dotenv import load_dotenv

from oracle.db.schema import get_connection, get_write_mode
from oracle.enrichers import musicbrainz, acoustid, discogs, lastfm, genius

logger = logging.getLogger(__name__)


def _cache_key(provider: str, track_id: str) -> str:
    return f"{provider}:{track_id}"


def _get_track(cursor, track_id: str):
    cursor.execute(
        "SELECT artist, title, album, year, duration, filepath FROM tracks WHERE track_id = ?",
        (track_id,)
    )
    return cursor.fetchone()


def _get_cached(cursor, provider: str, key: str) -> Optional[Dict]:
    cursor.execute(
        "SELECT payload_json FROM enrich_cache WHERE provider = ? AND lookup_key = ?",
        (provider, key)
    )
    row = cursor.fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _set_cached(cursor, provider: str, key: str, payload: Dict) -> None:
    cursor.execute(
        """
        INSERT OR REPLACE INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
        VALUES (?, ?, ?, ?)
        """,
        (provider, key, json.dumps(payload), time.time())
    )


def _apply_lastfm_tags(cursor, track_id: str, payload: Dict) -> None:
    tags = payload.get("tags") if isinstance(payload, dict) else None
    if not isinstance(tags, list) or not tags:
        return
    clean_tags = [str(t).strip().lower() for t in tags if str(t).strip()]
    if not clean_tags:
        return
    genre = clean_tags[0]
    subgenres = ",".join(clean_tags[:5])
    cursor.execute(
        """
        UPDATE tracks
        SET genre = CASE WHEN genre IS NULL OR trim(genre) = '' THEN ? ELSE genre END,
            subgenres = CASE WHEN subgenres IS NULL OR trim(subgenres) = '' THEN ? ELSE subgenres END,
            metadata_source = COALESCE(metadata_source, 'lastfm'),
            last_enriched_at = ?
        WHERE track_id = ?
        """,
        (genre, subgenres, time.time(), track_id),
    )


def enrich_track(track_id: str, providers: Optional[List[str]] = None) -> Dict:
    if get_write_mode() != "apply_allowed":
        return {"error": "WRITE BLOCKED"}

    providers = providers or ["musicbrainz", "acoustid", "discogs", "lastfm", "genius"]

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()

    row = _get_track(cursor, track_id)
    if not row:
        conn.close()
        return {"error": "track not found"}

    artist, title, album, year, duration, filepath = row
    summary: Dict[str, Dict] = {}

    if "musicbrainz" in providers and artist and title:
        key = _cache_key("musicbrainz", track_id)
        cached = _get_cached(cursor, "musicbrainz", key)
        if cached is None:
            payload = musicbrainz.search_recording(artist, title, album, duration)
            if payload:
                _set_cached(cursor, "musicbrainz", key, payload)
            summary["musicbrainz"] = payload
        else:
            summary["musicbrainz"] = cached

    if "acoustid" in providers and filepath:
        key = _cache_key("acoustid", track_id)
        cached = _get_cached(cursor, "acoustid", key)
        if cached is None:
            fp = acoustid.fingerprint_file(filepath)
            if fp:
                fingerprint, fp_duration = fp
                payload = acoustid.lookup_fingerprint(fingerprint, fp_duration)
                if payload:
                    _set_cached(cursor, "acoustid", key, payload)
                summary["acoustid"] = payload
        else:
            summary["acoustid"] = cached

    if "discogs" in providers and artist and album:
        key = _cache_key("discogs", track_id)
        cached = _get_cached(cursor, "discogs", key)
        if cached is None:
            payload = discogs.search_release(artist, album, year)
            if payload:
                _set_cached(cursor, "discogs", key, payload)
            summary["discogs"] = payload
        else:
            summary["discogs"] = cached

    if "lastfm" in providers and artist and title:
        key = _cache_key("lastfm", track_id)
        cached = _get_cached(cursor, "lastfm", key)
        if cached is None:
            payload = lastfm.build_track_profile(artist, title)
            if payload:
                _set_cached(cursor, "lastfm", key, payload)
            summary["lastfm"] = payload
            _apply_lastfm_tags(cursor, track_id, payload)
        else:
            summary["lastfm"] = cached

    if "genius" in providers and artist and title:
        key = _cache_key("genius", track_id)
        cached = _get_cached(cursor, "genius", key)
        if cached is None:
            payload = genius.build_song_profile(artist, title)
            if payload:
                _set_cached(cursor, "genius", key, payload)
            summary["genius"] = payload
        else:
            summary["genius"] = cached

    conn.commit()
    conn.close()
    logger.debug("enrich_track %s providers=%s", track_id, ",".join(providers))
    return summary


if __name__ == "__main__":
    load_dotenv(override=True)
    print("Unified enricher ready")
