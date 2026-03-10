"""Player event bus for backend-driven playback state updates."""

from __future__ import annotations

from queue import Full, Queue
from threading import Lock
from typing import Any


class PlayerEventBus:
    """Fan-out event bus with bounded per-subscriber queues."""

    def __init__(self, max_queue_size: int = 128) -> None:
        self._max_queue_size = max_queue_size
        self._subscribers: list[Queue[dict[str, Any]]] = []
        self._lock = Lock()

    def subscribe(self) -> Queue[dict[str, Any]]:
        """Create and return a new subscriber queue."""
        queue: Queue[dict[str, Any]] = Queue(maxsize=self._max_queue_size)
        with self._lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue if present."""
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        """Publish an event to all active subscribers."""
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except Full:
                try:
                    queue.get_nowait()
                except Exception:
                    continue
                try:
                    queue.put_nowait(payload)
                except Full:
                    continue
