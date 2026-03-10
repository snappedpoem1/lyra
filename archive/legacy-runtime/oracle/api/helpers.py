"""Shared helper functions for the Lyra Oracle API blueprints.

Pure utilities — no Flask, no Blueprint.  Import freely from any blueprint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from oracle.db.schema import get_connection


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Convert non-JSON-native objects (e.g. Path) into JSON-safe primitives."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _playlist_run_to_dict(run: Any) -> dict:
    """Convert a PlaylistRun Pydantic model to a Flask-json-safe dict."""
    if hasattr(run, "model_dump"):
        payload = run.model_dump()
    else:
        payload = run.dict()
    return _json_safe(payload)


def _fallback_vibe_narrative(tracks: List[Dict[str, str]], arc_type: str) -> str:
    """Deterministic fallback narrative when LLM is unavailable."""
    if not tracks:
        return f"{arc_type.title()} arc with no tracks available."
    first = tracks[0]
    last = tracks[-1]
    return (
        f"{arc_type.title()} arc across {len(tracks)} tracks, beginning with "
        f"{first.get('artist', '?')} - {first.get('title', '?')} and resolving at "
        f"{last.get('artist', '?')} - {last.get('title', '?')}."
    )


# ---------------------------------------------------------------------------
# Track / library DB helpers
# ---------------------------------------------------------------------------

def _track_row_to_dict(row: Any) -> dict:
    return {
        "track_id": row[0],
        "artist": row[1],
        "title": row[2],
        "album": row[3],
        "year": row[4],
        "version_type": row[5],
        "confidence": row[6],
        "duration": row[7],
        "filepath": row[8],
    }


def _load_track(track_id: str) -> Optional[dict]:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT track_id, artist, title, album, year, version_type, confidence, duration, filepath
        FROM tracks
        WHERE track_id = ?
        """,
        (track_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return _track_row_to_dict(row) if row else None


def _library_filter_state(
    query: str = "",
    artist: str = "",
    album: str = "",
) -> tuple:
    clauses: list = []
    params: list = []
    if query:
        like = f"%{query}%"
        clauses.append("(artist LIKE ? OR title LIKE ? OR album LIKE ?)")
        params.extend([like, like, like])
    if artist:
        clauses.append("artist = ?")
        params.append(artist)
    if album:
        clauses.append("COALESCE(album, '') = ?")
        params.append("" if album == "Singles / Unknown Album" else album)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _fetch_library_tracks(
    query: str = "",
    artist: str = "",
    album: str = "",
    limit: int = 200,
    offset: int = 0,
) -> list:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    where, params = _library_filter_state(query=query, artist=artist, album=album)
    cursor.execute(
        f"""
        SELECT track_id, artist, title, album, year, version_type, confidence, duration, filepath
        FROM tracks
        {where}
        ORDER BY artist COLLATE NOCASE ASC, album COLLATE NOCASE ASC, title COLLATE NOCASE ASC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "track_id": row[0],
            "artist": row[1],
            "title": row[2],
            "album": row[3],
            "year": row[4],
            "version_type": row[5],
            "confidence": row[6],
            "duration": row[7],
            "filepath": row[8],
            "file_exists": bool(row[8] and Path(row[8]).exists()),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Vibe detail helper
# ---------------------------------------------------------------------------

def _load_vibe_detail(name: str) -> Optional[dict]:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name, query_json, created_at, track_count
        FROM vibe_profiles
        WHERE name = ?
        """,
        (name,),
    )
    vibe_row = cursor.fetchone()
    if not vibe_row:
        conn.close()
        return None

    cursor.execute(
        """
        SELECT t.track_id, t.artist, t.title, t.album, t.year,
               t.version_type, t.confidence, t.duration, t.filepath
        FROM vibe_tracks vt
        JOIN tracks t ON vt.track_id = t.track_id
        WHERE vt.vibe_name = ?
        ORDER BY vt.position
        """,
        (name,),
    )
    track_rows = cursor.fetchall()
    cursor.execute(
        """
        SELECT name, query_json, created_at, track_count
        FROM vibe_profiles
        WHERE name != ?
        ORDER BY created_at DESC
        LIMIT 4
        """,
        (name,),
    )
    related_rows = cursor.fetchall()
    conn.close()

    query_data = json.loads(vibe_row[1]) if vibe_row[1] else {}
    tracks = [_track_row_to_dict(row) for row in track_rows]
    story_beats = [
        f"Lead thread seeded from: {query_data.get('query', 'saved vibe')}",
        f"Sequence runs {len(tracks)} tracks in saved order.",
        "Use Oracle mode to pivot without losing the thread.",
    ]
    arc = []
    for idx, _track in enumerate(tracks[:8], start=1):
        scale = max(1, len(tracks[:8]))
        energy = round(min(0.95, 0.3 + (idx / scale) * 0.45), 2)
        arc.append({
            "step": idx,
            "energy": energy,
            "valence": 0.52,
            "tension": round(0.38 + idx * 0.04, 2),
        })

    def _related(row: Any) -> dict:
        qd = json.loads(row[1]) if row[1] else {}
        return {
            "id": row[0],
            "kind": "vibe",
            "title": row[0],
            "subtitle": qd.get("query", "Saved vibe"),
            "narrative": f"Saved listening thread for {qd.get('query', 'your library')}.",
            "trackCount": int(row[3] or 0),
            "freshnessLabel": "Saved vibe",
            "coverMosaic": [row[0][:1].upper() or "L"],
            "emotionalSignature": [],
            "lastTouchedLabel": "Saved",
        }

    return {
        "id": vibe_row[0],
        "kind": "vibe",
        "title": vibe_row[0],
        "subtitle": query_data.get("query", "Saved vibe"),
        "narrative": _fallback_vibe_narrative(tracks, "saved thread"),
        "trackCount": int(vibe_row[3] or len(tracks)),
        "freshnessLabel": "Saved vibe",
        "coverMosaic": [vibe_row[0][:1].upper() or "L"],
        "emotionalSignature": [],
        "lastTouchedLabel": "Saved",
        "query": query_data.get("query", ""),
        "tracks": tracks,
        "storyBeats": story_beats,
        "arc": arc,
        "relatedPlaylists": [_related(row) for row in related_rows],
        "oraclePivots": [],
        "createdAt": vibe_row[2],
    }
