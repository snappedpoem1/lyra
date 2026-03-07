"""Companion Pulse — translates backend player events into companion-layer events.

The ``CompanionPulse`` class bridges the low-level ``PlayerEventBus`` (which
emits raw transport-layer events) to a higher-level narrative event stream
consumed by the companion UI and the ``/ws/companion`` SSE endpoint.

Translated event types
----------------------
* ``track_started``   — player began a new track
* ``track_finished``  — player finished a track
* ``queue_empty``     — player finished a track and the queue is now empty
* ``paused``          — playback moved from playing → paused
* ``resumed``         — playback moved from paused → playing
* ``provider_degraded``   — injected externally (e.g. acquisition watchdog)
* ``provider_recovered``  — injected externally
* ``acquisition_queued``  — injected externally (e.g. waterfall acquirer)
"""

from __future__ import annotations

import logging
import threading
from queue import Empty, Queue
from threading import Lock
from typing import Any

from oracle.player.events import PlayerEventBus
from oracle.player.service import get_player_service

logger = logging.getLogger(__name__)


class CompanionPulse:
    """Translate player bus events into companion-layer narrative events.

    A single background thread subscribes to the process-singleton
    ``PlayerService`` event bus, converts each relevant event into a
    companion envelope, and republishes it onto an internal
    ``PlayerEventBus`` that SSE subscribers read from.

    External callers may also inject provider/acquisition events via the
    ``publish_provider_event`` and ``publish_acquisition_event`` helpers.
    """

    def __init__(self) -> None:
        self._bus = PlayerEventBus()
        self._lock = Lock()
        self._listening = False
        self._listener_thread: threading.Thread | None = None
        self._last_status: str = ""

    # ------------------------------------------------------------------
    # Subscription (downstream consumers — SSE endpoint)
    # ------------------------------------------------------------------

    def subscribe(self) -> Queue[dict[str, Any]]:
        """Register a downstream subscriber; returns a bounded queue."""
        return self._bus.subscribe()

    def unsubscribe(self, queue: Queue[dict[str, Any]]) -> None:
        """Deregister a downstream subscriber queue."""
        self._bus.unsubscribe(queue)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background listener thread (idempotent)."""
        with self._lock:
            if self._listening:
                return
            self._listening = True
            self._listener_thread = threading.Thread(
                target=self._listener_loop,
                name="companion-pulse-listener",
                daemon=True,
            )
            self._listener_thread.start()
        logger.info("[companion] pulse listener started")

    def stop(self) -> None:
        """Signal the background listener to stop."""
        with self._lock:
            self._listening = False
        logger.info("[companion] pulse listener stop requested")

    # ------------------------------------------------------------------
    # External injection helpers
    # ------------------------------------------------------------------

    def publish_provider_event(
        self,
        provider: str,
        state: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Inject a provider_degraded or provider_recovered companion event.

        Args:
            provider: Human-readable provider name (e.g. ``"MusicBrainz"``).
            state: ``"degraded"`` or ``"recovered"``.
            details: Optional extra context keys merged into the envelope.
        """
        if state not in ("degraded", "recovered"):
            logger.warning("[companion] unknown provider state %r — ignored", state)
            return
        self._bus.publish(
            {
                "event_type": f"provider_{state}",
                "context": {"provider": provider, **(details or {})},
            }
        )

    def publish_acquisition_event(self, artist: str, title: str) -> None:
        """Inject an acquisition_queued companion event.

        Args:
            artist: Artist name for the queued acquisition.
            title: Track title for the queued acquisition.
        """
        self._bus.publish(
            {
                "event_type": "acquisition_queued",
                "context": {"artist": artist, "title": title},
            }
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _listener_loop(self) -> None:
        """Block on the player bus and forward translated events."""
        service = get_player_service()
        subscription = service.subscribe()
        try:
            while self._listening:
                try:
                    event = subscription.get(timeout=5.0)
                except Empty:
                    continue
                except Exception as exc:
                    logger.warning("[companion] queue read error: %s", exc)
                    continue
                try:
                    self._translate(event)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[companion] translation error for %r: %s", event, exc)
        finally:
            service.unsubscribe(subscription)
            logger.debug("[companion] listener loop exited")

    def _translate(self, event: dict[str, Any]) -> None:
        """Convert a raw player event into zero or more companion envelopes."""
        event_type = event.get("event_type", "")

        if event_type == "player_track_started":
            track = event.get("track") or {}
            self._last_status = "playing"
            self._bus.publish(
                {
                    "event_type": "track_started",
                    "context": {
                        "artist": track.get("artist", ""),
                        "title": track.get("title", ""),
                        "album": track.get("album", ""),
                    },
                }
            )

        elif event_type == "player_track_finished":
            track = event.get("track") or {}
            self._bus.publish(
                {
                    "event_type": "track_finished",
                    "context": {
                        "artist": track.get("artist", ""),
                        "title": track.get("title", ""),
                    },
                }
            )

        elif event_type == "player_queue_changed":
            queue = event.get("queue") or {}
            if queue.get("count", -1) == 0:
                self._bus.publish({"event_type": "queue_empty", "context": {}})

        elif event_type == "player_state_changed":
            state = event.get("state") or {}
            new_status = state.get("status", "")
            if new_status == "paused" and self._last_status == "playing":
                self._bus.publish({"event_type": "paused", "context": {}})
            elif new_status == "playing" and self._last_status == "paused":
                self._bus.publish({"event_type": "resumed", "context": {}})
            if new_status:
                self._last_status = new_status


# ------------------------------------------------------------------
# Process singleton
# ------------------------------------------------------------------

_companion_pulse_singleton: CompanionPulse | None = None
_companion_pulse_lock = Lock()


def get_companion_pulse() -> CompanionPulse:
    """Return the process-singleton ``CompanionPulse``, starting it on first call."""
    global _companion_pulse_singleton
    with _companion_pulse_lock:
        if _companion_pulse_singleton is None:
            _companion_pulse_singleton = CompanionPulse()
            _companion_pulse_singleton.start()
        return _companion_pulse_singleton
