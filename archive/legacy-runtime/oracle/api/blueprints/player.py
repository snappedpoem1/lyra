"""Canonical backend player API blueprint."""

from __future__ import annotations

import json
import logging
from queue import Empty
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context

from oracle.player.service import get_player_service

logger = logging.getLogger(__name__)

bp = Blueprint("player", __name__)


def _error(message: str, status_code: int) -> tuple[Response, int]:
    return jsonify({"error": message}), status_code


def _parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a boolean")


def _parse_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


@bp.route("/api/player/state", methods=["GET"])
def api_player_state() -> tuple[Response, int] | Response:
    service = get_player_service()
    return jsonify(service.get_state())


@bp.route("/api/player/queue", methods=["GET"])
def api_player_queue() -> tuple[Response, int] | Response:
    service = get_player_service()
    return jsonify(service.get_queue())


@bp.route("/api/player/play", methods=["POST"])
def api_player_play() -> tuple[Response, int] | Response:
    service = get_player_service()
    if not service.engine_available:
        return _error("player engine unavailable", 503)
    data = request.get_json(silent=True) or {}
    try:
        track_id = data.get("track_id")
        queue_index = data.get("queue_index")
        payload = service.play(
            track_id=str(track_id).strip() if track_id is not None else None,
            queue_index=_parse_int(queue_index, "queue_index") if queue_index is not None else None,
        )
        return jsonify(payload)
    except KeyError:
        return _error("track not found", 404)
    except IndexError as exc:
        return _error(str(exc), 400)
    except ValueError as exc:
        return _error(str(exc), 400)
    except PermissionError as exc:
        return _error(str(exc), 503)
    except RuntimeError as exc:
        return _error(str(exc), 409)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player play failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/pause", methods=["POST"])
def api_player_pause() -> tuple[Response, int] | Response:
    service = get_player_service()
    if not service.engine_available:
        return _error("player engine unavailable", 503)
    try:
        payload = service.pause()
        return jsonify(payload)
    except RuntimeError as exc:
        return _error(str(exc), 409)
    except PermissionError as exc:
        return _error(str(exc), 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player pause failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/seek", methods=["POST"])
def api_player_seek() -> tuple[Response, int] | Response:
    service = get_player_service()
    if not service.engine_available:
        return _error("player engine unavailable", 503)
    data = request.get_json(silent=True) or {}
    try:
        position_ms = _parse_int(data.get("position_ms"), "position_ms")
        payload = service.seek(position_ms)
        return jsonify(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except RuntimeError as exc:
        return _error(str(exc), 409)
    except PermissionError as exc:
        return _error(str(exc), 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player seek failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/next", methods=["POST"])
def api_player_next() -> tuple[Response, int] | Response:
    service = get_player_service()
    if not service.engine_available:
        return _error("player engine unavailable", 503)
    try:
        payload = service.next_track()
        return jsonify(payload)
    except RuntimeError as exc:
        return _error(str(exc), 409)
    except PermissionError as exc:
        return _error(str(exc), 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player next failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/previous", methods=["POST"])
def api_player_previous() -> tuple[Response, int] | Response:
    service = get_player_service()
    if not service.engine_available:
        return _error("player engine unavailable", 503)
    try:
        payload = service.previous_track()
        return jsonify(payload)
    except RuntimeError as exc:
        return _error(str(exc), 409)
    except PermissionError as exc:
        return _error(str(exc), 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player previous failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/queue/add", methods=["POST"])
def api_player_queue_add() -> tuple[Response, int] | Response:
    service = get_player_service()
    data = request.get_json(silent=True) or {}
    track_id = str(data.get("track_id") or "").strip()
    if not track_id:
        return _error("track_id is required", 400)
    try:
        at_index = data.get("at_index")
        payload = service.add_to_queue(
            track_id=track_id,
            at_index=_parse_int(at_index, "at_index") if at_index is not None else None,
        )
        return jsonify(payload)
    except KeyError:
        return _error("track not found", 404)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("queue add failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/queue/reorder", methods=["POST"])
def api_player_queue_reorder() -> tuple[Response, int] | Response:
    service = get_player_service()
    data = request.get_json(silent=True) or {}
    ordered_track_ids = data.get("ordered_track_ids")
    if not isinstance(ordered_track_ids, list):
        return _error("ordered_track_ids must be an array", 400)
    try:
        payload = service.reorder_queue([str(track_id) for track_id in ordered_track_ids])
        return jsonify(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("queue reorder failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/mode", methods=["POST"])
def api_player_mode() -> tuple[Response, int] | Response:
    service = get_player_service()
    data = request.get_json(silent=True) or {}
    try:
        shuffle = _parse_bool(data["shuffle"], "shuffle") if "shuffle" in data else None
        repeat_mode = str(data["repeat_mode"]) if "repeat_mode" in data else None
        payload = service.set_mode(shuffle=shuffle, repeat_mode=repeat_mode)
        return jsonify(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player mode failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/volume", methods=["POST"])
def api_player_volume() -> tuple[Response, int] | Response:
    service = get_player_service()
    data = request.get_json(silent=True) or {}
    try:
        raw = data.get("volume")
        if raw is None:
            return _error("volume is required", 400)
        volume = float(raw)
        payload = service.set_volume(volume)
        return jsonify(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player volume failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


@bp.route("/api/player/queue/clear", methods=["POST"])
def api_player_queue_clear() -> tuple[Response, int] | Response:
    service = get_player_service()
    try:
        payload = service.clear_queue()
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("player queue clear failed: %s", exc)
        service.publish_error(str(exc))
        return _error("internal player error", 500)


def _stream_player_events() -> Any:
    service = get_player_service()
    subscription = service.subscribe()
    try:
        initial_state = {
            "type": "player_state_changed",
            "ts": service.get_state().get("updated_at"),
            "state": service.get_state(),
        }
        initial_queue = {
            "type": "player_queue_changed",
            "ts": service.get_state().get("updated_at"),
            "queue": service.get_queue(),
        }
        yield f"data: {json.dumps(initial_state)}\n\n"
        yield f"data: {json.dumps(initial_queue)}\n\n"
        while True:
            try:
                event = subscription.get(timeout=25.0)
            except Empty:
                yield "event: ping\ndata: {}\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        service.unsubscribe(subscription)


@bp.route("/ws/player", methods=["GET"])
def ws_player_events() -> Response:
    """Primary player event stream endpoint (SSE over HTTP)."""
    return Response(
        stream_with_context(_stream_player_events()),
        mimetype="text/event-stream",
    )
