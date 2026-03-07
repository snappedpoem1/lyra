"""Oracle action contract endpoints bound to canonical player service."""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from oracle.db.schema import get_connection, get_write_mode
from oracle.player.service import get_player_service
from oracle.radio import Radio

logger = logging.getLogger(__name__)

bp = Blueprint("oracle_actions", __name__)

_CHAOS_INTENSITY: float = 0.55
_CHAOS_LABELS: dict[str, float] = {
    "low": 0.25,
    "medium": 0.55,
    "high": 0.85,
}


def _parse_chaos_intensity(value: Any) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _CHAOS_LABELS:
            return _CHAOS_LABELS[normalized]
        value = normalized
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.intensity must be a float 0.0-1.0 or one of low|medium|high") from exc
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError("payload.intensity must be between 0.0 and 1.0")
    return parsed


def _chaos_count_for_intensity(intensity: float) -> int:
    if intensity < 0.34:
        return 1
    if intensity < 0.67:
        return 3
    return 5


def _run_vibe_generation(*, prompt: str, n: int, vibe_name: str | None) -> Any:
    from oracle.vibes import generate_vibe

    return generate_vibe(prompt, n=n, vibe_name=vibe_name)


def _run_playlust_generation(
    *,
    mood: str | None,
    duration_minutes: int,
    name: str | None,
    use_deepcut: bool,
) -> Any:
    from oracle.playlust import Playlust

    return Playlust().generate(
        mood=mood,
        duration_minutes=duration_minutes,
        name=name,
        use_deepcut=use_deepcut,
    )


def _run_chaos_selection(*, current_track_id: str | None, count: int) -> list[dict[str, Any]]:
    return Radio().get_chaos_track(current_track_id=current_track_id, count=count)


def _collect_track_paths_from_run(run: Any) -> list[str]:
    tracks = getattr(run, "tracks", None)
    if tracks is None and isinstance(run, dict):
        tracks = run.get("tracks", [])
    if not isinstance(tracks, list):
        return []
    paths: list[str] = []
    for track in tracks:
        path_value = getattr(track, "path", None)
        if path_value is None and isinstance(track, dict):
            path_value = track.get("path")
        if isinstance(path_value, str) and path_value.strip():
            paths.append(path_value.strip())
    return paths


def _resolve_track_id_for_path(path: str) -> str | None:
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT track_id FROM tracks WHERE filepath = ? LIMIT 1", (path,))
        row = cursor.fetchone()
        if row:
            return str(row[0])
        cursor.execute("SELECT track_id FROM tracks WHERE LOWER(filepath) = LOWER(?) LIMIT 1", (path,))
        row = cursor.fetchone()
        if row:
            return str(row[0])
        return None
    finally:
        conn.close()


def _queue_track_ids(service: Any, track_ids: list[str]) -> dict[str, Any]:
    deduped_ids: list[str] = []
    seen: set[str] = set()
    for track_id in track_ids:
        normalized = str(track_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_ids.append(normalized)

    queue_result: dict[str, Any] | None = None
    for track_id in deduped_ids:
        queue_result = service.add_to_queue(track_id)

    return {
        "queued_track_ids": deduped_ids,
        "queued_count": len(deduped_ids),
        "queue": queue_result,
    }


def _queue_run_tracks(service: Any, run: Any) -> dict[str, Any]:
    paths = _collect_track_paths_from_run(run)
    track_ids: list[str] = []
    missing_paths: list[str] = []
    for path in paths:
        track_id = _resolve_track_id_for_path(path)
        if track_id:
            track_ids.append(track_id)
        else:
            missing_paths.append(path)
    queued = _queue_track_ids(service, track_ids)
    queued["missing_paths"] = missing_paths
    queued["run_track_count"] = len(paths)
    return queued


def _library_track_exists_for_artist_title(artist: str, title: str) -> str | None:
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT track_id
            FROM tracks
            WHERE status = 'active'
              AND LOWER(artist) = LOWER(?)
              AND LOWER(title) = LOWER(?)
            ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC
            LIMIT 1
            """,
            (artist.strip(), title.strip()),
        ).fetchone()
    finally:
        conn.close()
    return str(row[0]).strip() if row and row[0] else None


def _get_tracks_by_artist(artist: str, limit: int = 200) -> list[str]:
    """Return active track_ids for a given artist, ordered by album + track number."""
    conn = get_connection(timeout=10.0)
    try:
        rows = conn.cursor().execute(
            """
            SELECT track_id
            FROM tracks
            WHERE status = 'active'
              AND LOWER(artist) = LOWER(?)
            ORDER BY LOWER(album), COALESCE(track_number, 999), LOWER(title)
            LIMIT ?
            """,
            (artist.strip(), limit),
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _get_tracks_by_album(album: str, artist: str | None, limit: int = 200) -> list[str]:
    """Return active track_ids on a given album, ordered by track number."""
    conn = get_connection(timeout=10.0)
    try:
        if artist:
            rows = conn.cursor().execute(
                """
                SELECT track_id
                FROM tracks
                WHERE status = 'active'
                  AND LOWER(album) = LOWER(?)
                  AND LOWER(artist) = LOWER(?)
                ORDER BY COALESCE(track_number, 999), LOWER(title)
                LIMIT ?
                """,
                (album.strip(), artist.strip(), limit),
            ).fetchall()
        else:
            rows = conn.cursor().execute(
                """
                SELECT track_id
                FROM tracks
                WHERE status = 'active'
                  AND LOWER(album) = LOWER(?)
                ORDER BY COALESCE(track_number, 999), LOWER(title)
                LIMIT ?
                """,
                (album.strip(), limit),
            ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _get_similar_track_ids(track_id: str, limit: int = 20) -> list[str]:
    """Return track_ids from the similarity graph for the given seed track."""
    conn = get_connection(timeout=10.0)
    try:
        rows = conn.cursor().execute(
            """
            SELECT s.target_track_id
            FROM similar s
            JOIN tracks t ON t.track_id = s.target_track_id
            WHERE s.source_track_id = ?
              AND t.status = 'active'
            ORDER BY s.score DESC
            LIMIT ?
            """,
            (track_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _request_acquisition_for_lead(payload_dict: dict[str, Any]) -> dict[str, Any]:
    artist = str(payload_dict.get("artist") or "").strip()
    title = str(payload_dict.get("title") or "").strip()
    if not artist or not title:
        raise ValueError("payload.artist and payload.title are required")

    existing_track_id = _library_track_exists_for_artist_title(artist, title)
    if existing_track_id:
        return {
            "status": "already_owned",
            "action_type": "request_acquisition",
            "artist": artist,
            "title": title,
            "track_id": existing_track_id,
            "inserted": False,
        }

    provider = str(payload_dict.get("provider") or "oracle").strip() or "oracle"
    reason = str(payload_dict.get("reason") or "").strip()
    search_query = str(payload_dict.get("search_query") or f"{artist} {title}").strip()
    try:
        priority_score = float(payload_dict.get("score") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.score must be numeric when provided") from exc

    if get_write_mode() != "apply_allowed":
        return {
            "status": "write_blocked",
            "action_type": "request_acquisition",
            "artist": artist,
            "title": title,
            "provider": provider,
            "inserted": False,
        }

    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO acquisition_queue
                (artist, title, priority_score, source, search_query, playlist_name, status, added_at)
            SELECT ?, ?, ?, ?, ?, ?, 'pending', datetime('now')
            WHERE NOT EXISTS (
                SELECT 1
                FROM acquisition_queue
                WHERE LOWER(artist) = LOWER(?)
                  AND LOWER(title) = LOWER(?)
                  AND status != 'completed'
            )
            """,
            (
                artist,
                title,
                priority_score,
                f"oracle_broker:{provider}",
                search_query,
                "oracle_broker",
                artist,
                title,
            ),
        )
        inserted = cursor.rowcount > 0
        queue_id = int(cursor.lastrowid or 0) if inserted else None
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "queued" if inserted else "already_pending",
        "action_type": "request_acquisition",
        "artist": artist,
        "title": title,
        "provider": provider,
        "queue_id": queue_id,
        "inserted": inserted,
        "search_query": search_query,
        "reason": reason,
    }


def _execute_start_vibe(service: Any, payload_dict: dict[str, Any]) -> dict[str, Any]:
    prompt = str(payload_dict.get("prompt") or payload_dict.get("query") or "").strip()
    if not prompt:
        raise ValueError("payload.prompt or payload.query is required")
    try:
        n = int(payload_dict.get("n", 30))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.n must be an integer") from exc
    n = max(1, min(n, 200))
    vibe_name = str(payload_dict.get("name") or "").strip() or None
    run = _run_vibe_generation(prompt=prompt, n=n, vibe_name=vibe_name)
    queued = _queue_run_tracks(service, run)
    return {
        "status": "ok",
        "action_type": "start_vibe",
        "prompt": prompt,
        "run_uuid": getattr(run, "uuid", None),
        "queued_count": queued["queued_count"],
        "missing_paths": queued["missing_paths"],
        "queue": queued["queue"],
    }


def _execute_start_playlust(service: Any, payload_dict: dict[str, Any]) -> dict[str, Any]:
    mood_value = payload_dict.get("mood")
    mood = str(mood_value).strip() if mood_value is not None else None
    try:
        duration_minutes = int(payload_dict.get("duration_minutes", 60))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.duration_minutes must be an integer") from exc
    duration_minutes = max(10, min(duration_minutes, 240))
    name_value = payload_dict.get("name")
    name = str(name_value).strip() if name_value is not None else None
    use_deepcut = bool(payload_dict.get("use_deepcut", True))
    run = _run_playlust_generation(
        mood=mood,
        duration_minutes=duration_minutes,
        name=name,
        use_deepcut=use_deepcut,
    )
    queued = _queue_run_tracks(service, run)
    return {
        "status": "ok",
        "action_type": "start_playlust",
        "mood": mood,
        "duration_minutes": duration_minutes,
        "run_uuid": getattr(run, "uuid", None),
        "queued_count": queued["queued_count"],
        "missing_paths": queued["missing_paths"],
        "queue": queued["queue"],
    }


@bp.route("/api/oracle/context", methods=["GET"])
def api_oracle_context() -> tuple[Any, int] | Any:
    service = get_player_service()
    state = service.get_state()
    queue = service.get_queue()

    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ph.track_id, t.artist, t.title, ph.completion_rate, ph.skipped, ph.ts
            FROM playback_history ph
            LEFT JOIN tracks t ON t.track_id = ph.track_id
            ORDER BY ph.id DESC
            LIMIT 30
            """
        )
        recent_rows = cursor.fetchall()
        recent = [
            {
                "track_id": str(row[0]),
                "artist": str(row[1] or ""),
                "title": str(row[2] or ""),
                "completion_rate": float(row[3] or 0.0),
                "skipped": bool(row[4]),
                "ts": float(row[5] or 0.0),
            }
            for row in recent_rows
        ]

        cursor.execute("SELECT dimension, value, confidence FROM taste_profile ORDER BY dimension ASC")
        taste_rows = cursor.fetchall()
        taste_summary = {
            str(row[0]): {
                "value": float(row[1] or 0.0),
                "confidence": float(row[2] or 0.0),
            }
            for row in taste_rows
        }
    finally:
        conn.close()

    return jsonify(
        {
            "current_track": state.get("current_track"),
            "state": state,
            "queue": queue,
            "recent_playback": recent,
            "taste_summary": taste_summary,
            "chaos_intensity": _CHAOS_INTENSITY,
        }
    )


@bp.route("/api/oracle/chat", methods=["POST"])
def api_oracle_chat() -> tuple[Any, int] | Any:
    service = get_player_service()
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    mode = str(data.get("mode") or "ambient").strip().lower() or "ambient"
    context_scope = str(data.get("context_scope") or "player").strip().lower() or "player"

    if not message:
        return jsonify({"error": "message is required"}), 400

    state = service.get_state()
    queue = service.get_queue()
    current = state.get("current_track") or {}
    current_title = current.get("title") or "nothing loaded"
    current_artist = current.get("artist") or "unknown artist"

    response = (
        f"[{mode}] Current focus is {current_artist} - {current_title}. "
        f"Queue depth is {queue.get('count', 0)}. Ask me to queue, skip, pause, or pivot."
    )
    return jsonify(
        {
            "mode": mode,
            "context_scope": context_scope,
            "message": message,
            "response": response,
            "actionable": True,
        }
    )


@bp.route("/api/oracle/action/execute", methods=["POST"])
def api_oracle_action_execute() -> tuple[Any, int] | Any:
    global _CHAOS_INTENSITY

    service = get_player_service()
    if not service.engine_available:
        return jsonify({"error": "player engine unavailable"}), 503

    data = request.get_json(silent=True) or {}
    action_type = str(data.get("action_type") or "").strip().lower()
    payload = data.get("payload")
    payload_dict = payload if isinstance(payload, dict) else {}

    if not action_type:
        return jsonify({"error": "action_type is required"}), 400

    try:
        if action_type == "queue_tracks":
            track_ids = payload_dict.get("track_ids")
            if not isinstance(track_ids, list) or not track_ids:
                return jsonify({"error": "payload.track_ids must be a non-empty array"}), 400
            queued = _queue_track_ids(service, [str(track_id) for track_id in track_ids])
            return jsonify({"status": "ok", "action_type": action_type, **queued})

        if action_type == "play":
            state = service.play(
                track_id=str(payload_dict.get("track_id")).strip() if payload_dict.get("track_id") else None,
                queue_index=int(payload_dict["queue_index"]) if "queue_index" in payload_dict else None,
            )
            return jsonify({"status": "ok", "action_type": action_type, "state": state})

        if action_type == "pause":
            return jsonify({"status": "ok", "action_type": action_type, "state": service.pause()})

        if action_type == "next":
            return jsonify({"status": "ok", "action_type": action_type, "state": service.next_track()})

        if action_type == "previous":
            return jsonify({"status": "ok", "action_type": action_type, "state": service.previous_track()})

        if action_type == "switch_chaos_intensity":
            intensity = _parse_chaos_intensity(payload_dict.get("intensity"))
            _CHAOS_INTENSITY = intensity
            if bool(payload_dict.get("queue_now", False)):
                state = service.get_state()
                current = state.get("current_track") or {}
                current_track_id = str(current.get("track_id") or "").strip() or None
                chaos_rows = _run_chaos_selection(
                    current_track_id=current_track_id,
                    count=_chaos_count_for_intensity(intensity),
                )
                chaos_ids = [str(row.get("track_id") or "").strip() for row in chaos_rows]
                queued = _queue_track_ids(service, chaos_ids)
                return jsonify(
                    {
                        "status": "ok",
                        "action_type": action_type,
                        "chaos_intensity": intensity,
                        "queued_now": True,
                        **queued,
                    }
                )
            return jsonify(
                {
                    "status": "ok",
                    "action_type": action_type,
                    "chaos_intensity": intensity,
                    "queued_now": False,
                }
            )

        if action_type == "start_vibe":
            return jsonify(_execute_start_vibe(service, payload_dict))

        if action_type == "start_playlust":
            return jsonify(_execute_start_playlust(service, payload_dict))

        if action_type == "request_acquisition":
            return jsonify(_request_acquisition_for_lead(payload_dict))

        if action_type == "resume":
            return jsonify({"status": "ok", "action_type": action_type, "state": service.play()})

        if action_type == "set_volume":
            raw = payload_dict.get("volume")
            if raw is None:
                return jsonify({"error": "payload.volume is required"}), 400
            try:
                state = service.set_volume(float(raw))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"status": "ok", "action_type": action_type, "state": state})

        if action_type == "set_shuffle":
            shuffle = bool(payload_dict.get("enabled", payload_dict.get("shuffle", False)))
            return jsonify(
                {"status": "ok", "action_type": action_type, "state": service.set_mode(shuffle=shuffle)}
            )

        if action_type == "set_repeat":
            mode = str(payload_dict.get("mode", payload_dict.get("repeat_mode", "off")))
            return jsonify(
                {"status": "ok", "action_type": action_type, "state": service.set_mode(repeat_mode=mode)}
            )

        if action_type == "clear_queue":
            return jsonify({"status": "ok", "action_type": action_type, "state": service.clear_queue()})

        if action_type == "play_artist":
            artist = str(payload_dict.get("artist") or "").strip()
            if not artist:
                return jsonify({"error": "payload.artist is required"}), 400
            track_ids = _get_tracks_by_artist(artist)
            if not track_ids:
                return jsonify({"error": f"no active tracks found for artist: {artist}"}), 404
            queued = _queue_track_ids(service, track_ids)
            service.play()
            return jsonify({"status": "ok", "action_type": action_type, "artist": artist, **queued})

        if action_type == "play_album":
            album = str(payload_dict.get("album") or "").strip()
            if not album:
                return jsonify({"error": "payload.album is required"}), 400
            artist_filter = str(payload_dict.get("artist") or "").strip() or None
            track_ids = _get_tracks_by_album(album, artist_filter)
            if not track_ids:
                return jsonify({"error": f"no active tracks found for album: {album}"}), 404
            queued = _queue_track_ids(service, track_ids)
            service.play()
            return jsonify({"status": "ok", "action_type": action_type, "album": album, **queued})

        if action_type == "play_similar":
            state = service.get_state()
            current = (state.get("current_track") or {}) if isinstance(state, dict) else {}
            current_id = str(current.get("track_id") or "").strip() or None
            if not current_id:
                return jsonify({"error": "no current track to find similar for"}), 409
            track_ids = _get_similar_track_ids(current_id)
            if not track_ids:
                return jsonify({"error": "no similar tracks found for current track"}), 404
            queued = _queue_track_ids(service, track_ids)
            return jsonify(
                {"status": "ok", "action_type": action_type, "source_track_id": current_id, **queued}
            )

        if action_type == "create_playlist":
            from oracle.api.blueprints.playlists import _create_playlist, _add_tracks_to_playlist
            name = str(payload_dict.get("name") or "").strip()
            if not name:
                return jsonify({"error": "payload.name is required"}), 400
            description = str(payload_dict.get("description") or "").strip()
            pl = _create_playlist(name, description)
            seed_ids: list[str] = [str(t) for t in (payload_dict.get("track_ids") or []) if t]
            if seed_ids:
                _add_tracks_to_playlist(pl["id"], seed_ids)
                pl["track_count"] = len(seed_ids)
            return jsonify({"status": "ok", "action_type": action_type, "playlist": pl})

        if action_type == "add_to_playlist":
            from oracle.api.blueprints.playlists import _add_tracks_to_playlist
            playlist_id = str(payload_dict.get("playlist_id") or "").strip()
            if not playlist_id:
                return jsonify({"error": "payload.playlist_id is required"}), 400
            track_ids_raw: list[str] = [str(t) for t in (payload_dict.get("track_ids") or []) if t]
            if not track_ids_raw:
                return jsonify({"error": "payload.track_ids is required"}), 400
            inserted = _add_tracks_to_playlist(playlist_id, track_ids_raw)
            return jsonify({"status": "ok", "action_type": action_type,
                            "playlist_id": playlist_id, "inserted": inserted})

        if action_type == "play_playlist":
            from oracle.api.blueprints.playlists import _get_playlist_track_ids
            playlist_id = str(payload_dict.get("playlist_id") or "").strip()
            if not playlist_id:
                return jsonify({"error": "payload.playlist_id is required"}), 400
            track_ids_pl = _get_playlist_track_ids(playlist_id)
            if not track_ids_pl:
                return jsonify({"error": "playlist is empty or has no active tracks"}), 404
            queued_pl = _queue_track_ids(service, track_ids_pl)
            state_pl = service.play()
            return jsonify({"status": "ok", "action_type": action_type,
                            "playlist_id": playlist_id, "state": state_pl, **queued_pl})

        if action_type == "list_playlists":
            from oracle.api.blueprints.playlists import _list_saved_playlists
            playlists = _list_saved_playlists()
            return jsonify({"status": "ok", "action_type": action_type,
                            "playlists": playlists, "count": len(playlists)})

        return jsonify({"error": f"unsupported action_type: {action_type}"}), 400
    except KeyError:
        return jsonify({"error": "track not found"}), 404
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 503
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("oracle action execute failed: %s", exc)
        service.publish_error(str(exc))
        return jsonify({"error": "oracle action failed"}), 500
