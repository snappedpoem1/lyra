"""Companion Pulse API blueprint — /ws/companion SSE endpoint."""

from __future__ import annotations

import json
import logging
from queue import Empty
from typing import Any

from flask import Blueprint, Response, stream_with_context

from oracle.companion.pulse import get_companion_pulse

logger = logging.getLogger(__name__)

bp = Blueprint("companion", __name__)


def _stream_companion_events() -> Any:
    pulse = get_companion_pulse()
    subscription = pulse.subscribe()
    try:
        while True:
            try:
                event = subscription.get(timeout=25.0)
            except Empty:
                yield "event: ping\ndata: {}\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        pulse.unsubscribe(subscription)


@bp.route("/ws/companion", methods=["GET"])
def ws_companion_events() -> Response:
    """Companion Pulse SSE stream.

    Clients connect and receive a stream of companion-layer narrative events:
    ``track_started``, ``track_finished``, ``queue_empty``, ``paused``,
    ``resumed``, ``provider_degraded``, ``provider_recovered``,
    ``acquisition_queued``.  A ``ping`` keep-alive is emitted every 25 s.
    """
    return Response(
        stream_with_context(_stream_companion_events()),
        mimetype="text/event-stream",
    )
