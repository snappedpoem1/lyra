"""Unified metadata enrichment pipeline."""

from __future__ import annotations

from typing import Dict, List, Optional
import json
import time

from dotenv import load_dotenv

from oracle.db.schema import get_connection, get_write_mode
from oracle.enrichers import musicbrainz, acoustid, discogs


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


def enrich_track(track_id: str, providers: Optional[List[str]] = None) -> Dict:
    if get_write_mode() != "apply_allowed":
        return {"error": "WRITE BLOCKED"}

    providers = providers or ["musicbrainz", "acoustid", "discogs"]

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
                _set_cached(cursor, "acoustid", key, payload)
                summary["acoustid"] = payload
        else:
            summary["acoustid"] = cached

    if "discogs" in providers and artist and album:
        key = _cache_key("discogs", track_id)
        cached = _get_cached(cursor, "discogs", key)
        if cached is None:
            payload = discogs.search_release(artist, album, year)
            _set_cached(cursor, "discogs", key, payload)
            summary["discogs"] = payload
        else:
            summary["discogs"] = cached

    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    load_dotenv(override=True)
    print("Unified enricher ready")
