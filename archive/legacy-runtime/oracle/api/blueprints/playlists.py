"""Named user-playlist CRUD + play blueprint (Wave 13 / SPEC-012)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from flask import Blueprint, jsonify, request

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

bp = Blueprint("playlists", __name__)


# ── DB helpers ────────────────────────────────────────────────────────────


def _playlist_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "name": str(row[1]),
        "description": str(row[2] or ""),
        "track_count": int(row[3] or 0),
        "created_at": float(row[4] or 0),
        "updated_at": float(row[5] or 0),
    }


def _list_saved_playlists() -> list[dict[str, Any]]:
    conn = get_connection(timeout=10.0)
    try:
        rows = conn.cursor().execute(
            """
            SELECT p.id, p.name, p.description,
                   COUNT(pt.track_id) AS track_count,
                   p.created_at, p.updated_at
            FROM saved_playlists p
            LEFT JOIN saved_playlist_tracks pt ON pt.playlist_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [_playlist_row_to_dict(r) for r in rows]


def _get_playlist_with_tracks(playlist_id: str) -> dict[str, Any] | None:
    conn = get_connection(timeout=10.0)
    try:
        row = conn.cursor().execute(
            """
            SELECT p.id, p.name, p.description,
                   (SELECT COUNT(*) FROM saved_playlist_tracks WHERE playlist_id = p.id),
                   p.created_at, p.updated_at
            FROM saved_playlists p
            WHERE p.id = ?
            """,
            (playlist_id,),
        ).fetchone()
        if not row:
            return None
        pl = _playlist_row_to_dict(row)
        track_rows = conn.cursor().execute(
            """
            SELECT t.track_id, t.artist, t.title, t.album,
                   t.duration_ms, t.filepath, t.track_number,
                   pt.position
            FROM saved_playlist_tracks pt
            JOIN tracks t ON t.track_id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position, pt.added_at
            """,
            (playlist_id,),
        ).fetchall()
        pl["tracks"] = [
            {
                "track_id": str(r[0]),
                "artist": str(r[1] or ""),
                "title": str(r[2] or ""),
                "album": str(r[3] or ""),
                "duration_ms": int(r[4] or 0),
                "filepath": str(r[5] or ""),
                "track_number": r[6],
                "position": int(r[7] or 0),
            }
            for r in track_rows
        ]
        return pl
    finally:
        conn.close()


def _create_playlist(name: str, description: str) -> dict[str, Any]:
    now = time.time()
    pl_id = str(uuid.uuid4())
    conn = get_connection(timeout=10.0)
    try:
        conn.execute(
            "INSERT INTO saved_playlists (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
            (pl_id, name.strip(), description.strip(), now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": pl_id, "name": name, "description": description,
            "track_count": 0, "created_at": now, "updated_at": now}


def _add_tracks_to_playlist(playlist_id: str, track_ids: list[str]) -> int:
    """Insert tracks; skip duplicates. Returns number of rows inserted."""
    if not track_ids:
        return 0
    conn = get_connection(timeout=10.0)
    try:
        # Determine current max position
        row = conn.cursor().execute(
            "SELECT COALESCE(MAX(position), -1) FROM saved_playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        next_pos = int(row[0]) + 1
        now = time.time()
        inserted = 0
        for tid in track_ids:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO saved_playlist_tracks
                       (playlist_id, track_id, position, added_at) VALUES (?,?,?,?)""",
                    (playlist_id, tid, next_pos, now),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    next_pos += 1
                    inserted += 1
            except Exception:
                logger.warning("Could not add track %s to playlist %s", tid, playlist_id)
        conn.execute(
            "UPDATE saved_playlists SET updated_at = ? WHERE id = ?",
            (now, playlist_id),
        )
        conn.commit()
    finally:
        conn.close()
    return inserted


def _remove_track_from_playlist(playlist_id: str, track_id: str) -> bool:
    conn = get_connection(timeout=10.0)
    try:
        conn.execute(
            "DELETE FROM saved_playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        changed = conn.execute("SELECT changes()").fetchone()[0]
        if changed:
            conn.execute(
                "UPDATE saved_playlists SET updated_at = ? WHERE id = ?",
                (time.time(), playlist_id),
            )
        conn.commit()
    finally:
        conn.close()
    return bool(changed)


def _delete_playlist(playlist_id: str) -> bool:
    conn = get_connection(timeout=10.0)
    try:
        conn.execute("DELETE FROM saved_playlists WHERE id = ?", (playlist_id,))
        changed = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return bool(changed)


def _get_playlist_track_ids(playlist_id: str) -> list[str]:
    conn = get_connection(timeout=10.0)
    try:
        rows = conn.cursor().execute(
            """SELECT pt.track_id
               FROM saved_playlist_tracks pt
               JOIN tracks t ON t.track_id = pt.track_id
               WHERE pt.playlist_id = ? AND t.status = 'active'
               ORDER BY pt.position, pt.added_at""",
            (playlist_id,),
        ).fetchall()
    finally:
        conn.close()
    return [str(r[0]) for r in rows]


# ── Endpoints ─────────────────────────────────────────────────────────────


@bp.route("/api/playlists", methods=["GET"])
def api_playlists_list() -> Any:
    """List all user-saved named playlists."""
    return jsonify({"playlists": _list_saved_playlists()})


@bp.route("/api/playlists", methods=["POST"])
def api_playlists_create() -> Any:
    """Create a new named playlist."""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    description = str(body.get("description") or "").strip()
    pl = _create_playlist(name, description)
    track_ids: list[str] = [str(t) for t in (body.get("track_ids") or []) if t]
    if track_ids:
        _add_tracks_to_playlist(pl["id"], track_ids)
        pl["track_count"] = len(track_ids)
    return jsonify({"playlist": pl}), 201


@bp.route("/api/playlists/<playlist_id>", methods=["GET"])
def api_playlist_detail(playlist_id: str) -> Any:
    """Return named playlist detail. Falls back to vibe-backed playlist if not found."""
    try:
        pl = _get_playlist_with_tracks(playlist_id)
    except Exception:
        pl = None
    if pl:
        # Shape compatible with mapPlaylistDetail
        return jsonify({
            "id": pl["id"],
            "title": pl["name"],
            "subtitle": pl["description"],
            "narrative": pl["description"] or f"{pl['track_count']} tracks in this playlist.",
            "trackCount": pl["track_count"],
            "freshnessLabel": "Saved playlist",
            "coverMosaic": [pl["name"][0].upper() if pl["name"] else "L"],
            "arc": [],
            "tracks": pl["tracks"],
            "storyBeats": [],
            "oraclePivots": [],
            "relatedPlaylists": [],
        })
    # Fallback to vibe-backed detail for existing vibe playlists
    try:
        from oracle.api.helpers import _load_vibe_detail
        detail = _load_vibe_detail(playlist_id)
        if detail:
            return jsonify(detail)
    except Exception:
        pass
    return jsonify({"error": "playlist not found"}), 404


@bp.route("/api/playlists/<playlist_id>", methods=["DELETE"])
def api_playlist_delete(playlist_id: str) -> Any:
    """Delete a saved playlist."""
    if _delete_playlist(playlist_id):
        return jsonify({"status": "deleted", "id": playlist_id})
    return jsonify({"error": "playlist not found"}), 404


@bp.route("/api/playlists/<playlist_id>/tracks", methods=["POST"])
def api_playlist_add_tracks(playlist_id: str) -> Any:
    """Add tracks to a saved playlist."""
    # Verify playlist exists
    conn = get_connection(timeout=10.0)
    try:
        row = conn.cursor().execute(
            "SELECT id FROM saved_playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "playlist not found"}), 404

    body = request.get_json(silent=True) or {}
    track_ids = [str(t) for t in (body.get("track_ids") or []) if t]
    if not track_ids:
        return jsonify({"error": "track_ids is required"}), 400
    inserted = _add_tracks_to_playlist(playlist_id, track_ids)
    return jsonify({"status": "ok", "inserted": inserted, "playlist_id": playlist_id})


@bp.route("/api/playlists/<playlist_id>/tracks/<track_id>", methods=["DELETE"])
def api_playlist_remove_track(playlist_id: str, track_id: str) -> Any:
    """Remove a track from a saved playlist."""
    if _remove_track_from_playlist(playlist_id, track_id):
        return jsonify({"status": "removed", "playlist_id": playlist_id, "track_id": track_id})
    return jsonify({"error": "track not in playlist"}), 404


@bp.route("/api/playlists/<playlist_id>/play", methods=["POST"])
def api_playlist_play(playlist_id: str) -> Any:
    """Queue and play all active tracks in a saved playlist."""
    track_ids = _get_playlist_track_ids(playlist_id)
    if not track_ids:
        return jsonify({"error": "playlist is empty or has no active tracks"}), 404

    from oracle.player import get_player_service
    service = get_player_service()
    for tid in track_ids:
        service.add_to_queue(tid)
    state = service.play()
    return jsonify({
        "status": "ok",
        "playlist_id": playlist_id,
        "queued_count": len(track_ids),
        "state": state,
    })
