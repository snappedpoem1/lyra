"""Tests for oracle.companion.pulse — Wave 11 Companion Pulse.

All translation tests call ``CompanionPulse._translate()`` synchronously so
no threading is needed.  The companion bus is tested through a direct
subscriber queue produced by ``pulse.subscribe()``.
"""

from __future__ import annotations

from queue import Empty, Queue

from oracle.companion.pulse import CompanionPulse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pulse() -> tuple[CompanionPulse, Queue]:
    """Return a CompanionPulse (not started) and a subscribed queue."""
    pulse = CompanionPulse()
    q = pulse.subscribe()
    return pulse, q


def _drain(q: Queue) -> list[dict]:
    """Drain all items currently in a queue without blocking."""
    events: list[dict] = []
    while True:
        try:
            events.append(q.get_nowait())
        except Empty:
            break
    return events


# ---------------------------------------------------------------------------
# track_started
# ---------------------------------------------------------------------------


class TestTrackStarted:
    def test_emits_companion_event(self) -> None:
        pulse, q = _pulse()
        pulse._translate(
            {
                "event_type": "player_track_started",
                "track": {"artist": "Burial", "title": "Archangel", "album": "Untrue"},
                "state": {"status": "playing"},
            }
        )
        events = _drain(q)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "track_started"
        assert ev["context"]["artist"] == "Burial"
        assert ev["context"]["title"] == "Archangel"
        assert ev["context"]["album"] == "Untrue"

    def test_sets_last_status_to_playing(self) -> None:
        pulse, _ = _pulse()
        pulse._translate(
            {
                "event_type": "player_track_started",
                "track": {"artist": "A", "title": "B", "album": "C"},
            }
        )
        assert pulse._last_status == "playing"

    def test_missing_track_key_uses_empty_strings(self) -> None:
        pulse, q = _pulse()
        pulse._translate({"event_type": "player_track_started"})
        events = _drain(q)
        assert events[0]["context"] == {"artist": "", "title": "", "album": ""}


# ---------------------------------------------------------------------------
# track_finished
# ---------------------------------------------------------------------------


class TestTrackFinished:
    def test_emits_companion_event(self) -> None:
        pulse, q = _pulse()
        pulse._translate(
            {
                "event_type": "player_track_finished",
                "track": {"artist": "Boards of Canada", "title": "Roygbiv"},
            }
        )
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["event_type"] == "track_finished"
        assert events[0]["context"]["artist"] == "Boards of Canada"


# ---------------------------------------------------------------------------
# queue_empty
# ---------------------------------------------------------------------------


class TestQueueEmpty:
    def test_emits_when_count_is_zero(self) -> None:
        pulse, q = _pulse()
        pulse._translate(
            {"event_type": "player_queue_changed", "queue": {"items": [], "count": 0}}
        )
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["event_type"] == "queue_empty"

    def test_no_event_when_count_positive(self) -> None:
        pulse, q = _pulse()
        pulse._translate(
            {
                "event_type": "player_queue_changed",
                "queue": {"items": [{"track_id": "1"}], "count": 1},
            }
        )
        assert _drain(q) == []


# ---------------------------------------------------------------------------
# paused / resumed
# ---------------------------------------------------------------------------


class TestPausedResumed:
    def test_paused_emits_when_was_playing(self) -> None:
        pulse, q = _pulse()
        pulse._last_status = "playing"
        pulse._translate(
            {
                "event_type": "player_state_changed",
                "state": {"status": "paused"},
            }
        )
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["event_type"] == "paused"

    def test_resumed_emits_when_was_paused(self) -> None:
        pulse, q = _pulse()
        pulse._last_status = "paused"
        pulse._translate(
            {
                "event_type": "player_state_changed",
                "state": {"status": "playing"},
            }
        )
        events = _drain(q)
        assert events[0]["event_type"] == "resumed"

    def test_paused_not_emitted_from_stopped(self) -> None:
        pulse, q = _pulse()
        pulse._last_status = "stopped"
        pulse._translate(
            {
                "event_type": "player_state_changed",
                "state": {"status": "paused"},
            }
        )
        assert _drain(q) == []

    def test_state_unknown_event_type_ignored(self) -> None:
        pulse, q = _pulse()
        pulse._translate({"event_type": "player_position_tick", "state": {"status": "playing"}})
        assert _drain(q) == []


# ---------------------------------------------------------------------------
# External injection helpers
# ---------------------------------------------------------------------------


class TestProviderEvents:
    def test_provider_degraded(self) -> None:
        pulse, q = _pulse()
        pulse.publish_provider_event("MusicBrainz", "degraded")
        events = _drain(q)
        assert events[0]["event_type"] == "provider_degraded"
        assert events[0]["context"]["provider"] == "MusicBrainz"

    def test_provider_recovered(self) -> None:
        pulse, q = _pulse()
        pulse.publish_provider_event("MusicBrainz", "recovered")
        events = _drain(q)
        assert events[0]["event_type"] == "provider_recovered"

    def test_invalid_provider_state_ignored(self) -> None:
        pulse, q = _pulse()
        pulse.publish_provider_event("Foo", "broken")
        assert _drain(q) == []

    def test_acquisition_queued(self) -> None:
        pulse, q = _pulse()
        pulse.publish_acquisition_event("The Caretaker", "Stages of Dementia")
        events = _drain(q)
        assert events[0]["event_type"] == "acquisition_queued"
        assert events[0]["context"]["artist"] == "The Caretaker"
        assert events[0]["context"]["title"] == "Stages of Dementia"
