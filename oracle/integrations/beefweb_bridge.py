"""
PlayFaux — BeefWeb Real-time Playback Bridge (F-013)

Monitors foobar2000 via the BeefWeb REST API. When track changes are detected:
  1. Logs the completed track to playback_history with completion_rate and skip flag.
  2. Triggers taste profile update via oracle.taste.update_taste_from_playback.
  3. Optionally broadcasts an event dict for downstream consumers (radio, arc, etc.).

BeefWeb API assumed endpoint:  http://localhost:8080/api/player

BeefWeb must have the ``foo_beefweb`` plugin installed and enabled in foobar2000.
Port is configurable via BEEFWEB_PORT or the ``port`` argument.

Usage (run as a background service)::

    # CLI
    oracle listen [--host localhost] [--port 8880] [--interval 0.5]

    # Programmatic
    bridge = BeefWebBridge(port=8880)
    for event in bridge.stream_events():          # blocking generator
        print(event)                              # {"type": "track_start", ...}

    # Non-blocking background thread
    bridge = BeefWebBridge()
    bridge.start_background()
    # ... do other work ...
    bridge.stop()

Author: Lyra Oracle — Sprint 2, F-013
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Dict, Generator, List, Optional

import requests

from oracle.db.schema import get_connection, get_write_mode

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

BEEFWEB_HOST = os.getenv("BEEFWEB_HOST", "localhost")
BEEFWEB_PORT = int(os.getenv("BEEFWEB_PORT", "8880"))
BEEFWEB_POLL_INTERVAL = float(os.getenv("BEEFWEB_POLL_INTERVAL", "0.5"))

# Completion threshold below which a track is considered skipped
SKIP_THRESHOLD = float(os.getenv("BEEFWEB_SKIP_THRESHOLD", "0.5"))

# Taste learning weights
TASTE_WEIGHT_COMPLETED = float(os.getenv("TASTE_WEIGHT_COMPLETED", "1.0"))
TASTE_WEIGHT_SKIPPED = float(os.getenv("TASTE_WEIGHT_SKIPPED", "0.5"))

# Active-state column names returned by BeefWeb player endpoint
_BEEFWEB_COLUMNS = [
    "%artist%",
    "%title%",
    "%album%",
    "%track artist%",
    "%length_seconds_fp%",
]


class PlaybackEvent:
    """Structured playback event from the BeefWeb bridge."""

    __slots__ = ("type", "artist", "title", "album", "track_id", "position",
                 "duration", "completion_rate", "skipped", "ts")

    def __init__(
        self,
        event_type: str,
        artist: str = "",
        title: str = "",
        album: str = "",
        track_id: str = "",
        position: float = 0.0,
        duration: float = 0.0,
        completion_rate: float = 0.0,
        skipped: bool = False,
        ts: Optional[float] = None,
    ) -> None:
        self.type = event_type
        self.artist = artist
        self.title = title
        self.album = album
        self.track_id = track_id
        self.position = position
        self.duration = duration
        self.completion_rate = completion_rate
        self.skipped = skipped
        self.ts = ts or time.time()

    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "track_id": self.track_id,
            "position": self.position,
            "duration": self.duration,
            "completion_rate": round(self.completion_rate, 3),
            "skipped": self.skipped,
            "ts": self.ts,
        }

    def __repr__(self) -> str:
        return (
            f"PlaybackEvent({self.type!r}, artist={self.artist!r}, "
            f"title={self.title!r}, rate={self.completion_rate:.2f})"
        )


class BeefWebBridge:
    """
    Real-time beefweb polling bridge for foobar2000 + foo_beefweb.

    Emits playback events when tracks start, change, or the player stops.
    Automatically logs to playback_history and updates the taste profile.

    Args:
        host: BeefWeb host (default: ``BEEFWEB_HOST`` env var or ``localhost``).
        port: BeefWeb port (default: ``BEEFWEB_PORT`` env var or ``8880``).
        poll_interval: Seconds between polls (default: 0.5s).
        event_callback: Optional callable(PlaybackEvent) for custom handling.
        session_id: Optional session identifier stored in playback_history.
    """

    def __init__(
        self,
        host: str = BEEFWEB_HOST,
        port: int = BEEFWEB_PORT,
        poll_interval: float = BEEFWEB_POLL_INTERVAL,
        event_callback: Optional[Callable[[PlaybackEvent], None]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._base_url = f"http://{host}:{port}/api"
        self._interval = poll_interval
        self._callback = event_callback
        self._session_id = session_id or _generate_session_id()

        self._session = requests.Session()
        self._session.headers["User-Agent"] = "LyraOracle-PlayFaux/1.0"

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # State for change detection
        self._last_track_key: Optional[str] = None   # "{artist}|{title}"
        self._track_start_ts: float = 0.0
        self._track_start_position: float = 0.0
        self._last_position: float = 0.0
        self._last_duration: float = 0.0
        self._last_state: str = "stopped"

    # ─── Public API ────────────────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Return True if BeefWeb is reachable."""
        try:
            resp = self._session.get(f"{self._base_url}/player", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_current_track(self) -> Optional[Dict]:
        """
        Return the currently playing track info, or None if nothing is playing.

        Returns dict with keys: artist, title, album, position, duration, state
        """
        state = self._poll_player()
        if state is None:
            return None
        return {
            "artist": state.get("artist", ""),
            "title": state.get("title", ""),
            "album": state.get("album", ""),
            "position": state.get("position", 0.0),
            "duration": state.get("duration", 0.0),
            "state": state.get("state", "stopped"),
        }

    def stream_events(
        self, max_events: Optional[int] = None
    ) -> Generator[Dict, None, None]:
        """
        Blocking generator that yields PlaybackEvent dicts.

        Runs until ``stop()`` is called or ``max_events`` is reached.

        Example::

            bridge = BeefWebBridge()
            for event in bridge.stream_events():
                print(event)
        """
        self._running = True
        count = 0
        logger.info("BeefWeb bridge starting — polling %s every %.1fs", self._base_url, self._interval)

        while self._running:
            event = self._poll_step()
            if event:
                yield event.to_dict()
                count += 1
                if max_events and count >= max_events:
                    break
            time.sleep(self._interval)

    def start_background(self) -> None:
        """Start the bridge in a background daemon thread."""
        if self._running:
            logger.warning("BeefWeb bridge already running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._background_loop,
            name="playfaux-bridge",
            daemon=True,
        )
        self._thread.start()
        logger.info("BeefWeb bridge started (background thread)")

    def stop(self) -> None:
        """Stop the bridge."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("BeefWeb bridge stopped")

    # ─── Internal Loop ─────────────────────────────────────────────────────────

    def _background_loop(self) -> None:
        """Background thread entry point."""
        while self._running:
            try:
                self._poll_step()
            except Exception as exc:
                logger.debug("BeefWeb poll error: %s", exc)
            time.sleep(self._interval)

    def _poll_step(self) -> Optional[PlaybackEvent]:
        """
        Single poll cycle. Detects state changes and emits events.

        Returns:
            A PlaybackEvent if a noteworthy change occurred, else None.
        """
        state = self._poll_player()
        if state is None:
            return None

        current_key = f"{state.get('artist', '')}|{state.get('title', '')}"
        current_state = state.get("state", "stopped")
        position = float(state.get("position", 0.0))
        duration = float(state.get("duration", 1.0)) or 1.0

        event: Optional[PlaybackEvent] = None

        # Track changed → log the previous track's completion
        if current_key != self._last_track_key and self._last_track_key:
            # Compute completion for the track that just ended
            elapsed = time.time() - self._track_start_ts
            completion = min(1.0, elapsed / max(self._last_duration, 1.0))
            skipped = completion < SKIP_THRESHOLD

            prev_artist, prev_title = self._split_track_key(self._last_track_key)
            prev_track_id = self._resolve_track_id(prev_artist, prev_title)

            event = PlaybackEvent(
                event_type="track_end",
                artist=prev_artist,
                title=prev_title,
                track_id=prev_track_id,
                position=self._last_position,
                duration=self._last_duration,
                completion_rate=completion,
                skipped=skipped,
            )

            self._log_playback(event)
            self._update_taste(event)

            if self._callback:
                try:
                    self._callback(event)
                except Exception as exc:
                    logger.debug("Event callback error: %s", exc)

        # New track started
        if current_key != self._last_track_key and current_state != "stopped":
            self._last_track_key = current_key
            self._track_start_ts = time.time()
            self._track_start_position = position

            artist, title = self._split_track_key(current_key)
            track_id = self._resolve_track_id(artist, title)

            start_event = PlaybackEvent(
                event_type="track_start",
                artist=artist,
                title=title,
                track_id=track_id,
                position=position,
                duration=duration,
            )

            if self._callback:
                try:
                    self._callback(start_event)
                except Exception as exc:
                    logger.debug("Start event callback error: %s", exc)

            if event is None:
                event = start_event

        # Stopped → was playing
        if current_state == "stopped" and self._last_state != "stopped" and self._last_track_key:
            artist, title = self._split_track_key(self._last_track_key)
            elapsed = time.time() - self._track_start_ts
            completion = min(1.0, elapsed / max(self._last_duration, 1.0))
            skipped = completion < SKIP_THRESHOLD
            track_id = self._resolve_track_id(artist, title)

            stop_event = PlaybackEvent(
                event_type="playback_stop",
                artist=artist,
                title=title,
                track_id=track_id,
                position=self._last_position,
                duration=self._last_duration,
                completion_rate=completion,
                skipped=skipped,
            )
            self._log_playback(stop_event)
            self._update_taste(stop_event)
            self._last_track_key = None
            if event is None:
                event = stop_event

        # Update state
        self._last_position = position
        self._last_duration = duration
        self._last_state = current_state

        return event

    # ─── BeefWeb API ───────────────────────────────────────────────────────────

    def _poll_player(self) -> Optional[Dict]:
        """
        Poll the BeefWeb player endpoint. Returns normalised state dict or None.

        Queries ``/api/player?columns={columns}`` for current track metadata.
        """
        try:
            # Query active item columns; 1=columns param for current track metadata
            resp = self._session.get(
                f"{self._base_url}/player",
                params={"columns": ",".join(_BEEFWEB_COLUMNS)},
                timeout=3,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            player = data.get("player", {})
            pb_state = player.get("playbackState", "stopped")

            active = player.get("activeItem", {})
            position = float(active.get("position", 0.0))
            duration = float(active.get("duration", 0.0))

            columns = active.get("columns", [])
            # columns order matches _BEEFWEB_COLUMNS
            artist = columns[0] if len(columns) > 0 else ""
            title = columns[1] if len(columns) > 1 else ""
            album = columns[2] if len(columns) > 2 else ""

            return {
                "state": pb_state,
                "artist": artist,
                "title": title,
                "album": album,
                "position": position,
                "duration": duration,
            }
        except requests.exceptions.ConnectionError:
            logger.debug("BeefWeb: foobar2000 not running or BeefWeb not enabled")
            return None
        except Exception as exc:
            logger.debug("BeefWeb poll failed: %s", exc)
            return None

    # ─── Persistence ───────────────────────────────────────────────────────────

    def _log_playback(self, event: PlaybackEvent) -> None:
        """Write a playback event to playback_history."""
        if get_write_mode() != "apply_allowed":
            return
        if not event.track_id:
            return
        try:
            conn = get_connection(timeout=5.0)
            c = conn.cursor()
            c.execute(
                """INSERT INTO playback_history
                   (track_id, ts, context, session_id, skipped, completion_rate)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.track_id,
                    event.ts,
                    event.type,
                    self._session_id,
                    1 if event.skipped else 0,
                    event.completion_rate,
                ),
            )
            conn.commit()
            conn.close()
            logger.debug(
                "BeefWeb: logged %s (%s - %s, rate=%.2f, skip=%s)",
                event.type, event.artist, event.title, event.completion_rate, event.skipped,
            )
        except Exception as exc:
            logger.debug("playback_history insert failed: %s", exc)

    def _update_taste(self, event: PlaybackEvent) -> None:
        """Trigger taste profile update from a playback event."""
        if not event.track_id:
            return
        if event.completion_rate < 0.10:
            return  # Too short to learn from
        try:
            from oracle.taste import update_taste_from_playback
            positive = not event.skipped
            weight = (
                TASTE_WEIGHT_COMPLETED * event.completion_rate
                if positive
                else TASTE_WEIGHT_SKIPPED
            )
            update_taste_from_playback(event.track_id, positive=positive, weight=weight)
            logger.debug(
                "Taste update: %s (%s, weight=%.2f)",
                "positive" if positive else "negative",
                event.title,
                weight,
            )
        except Exception as exc:
            logger.debug("Taste update failed: %s", exc)

    # ─── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_track_id(self, artist: str, title: str) -> str:
        """
        Look up the track_id in the local library by artist + title match.

        Uses a LIKE query since foobar2000 metadata may differ slightly from
        the stored metadata. Returns empty string if not found.
        """
        if not artist and not title:
            return ""
        try:
            conn = get_connection(timeout=3.0)
            c = conn.cursor()
            c.execute(
                """SELECT track_id FROM tracks
                   WHERE artist LIKE ? AND title LIKE ?
                   LIMIT 1""",
                (f"%{artist}%", f"%{title}%"),
            )
            row = c.fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception as exc:
            logger.debug("track_id lookup failed for %s - %s: %s", artist, title, exc)
            return ""

    @staticmethod
    def _split_track_key(key: str) -> tuple:
        """Split '{artist}|{title}' back into (artist, title)."""
        parts = key.split("|", 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


# ─── Module-level singleton ────────────────────────────────────────────────────

_bridge_instance: Optional[BeefWebBridge] = None


def get_bridge(host: str = BEEFWEB_HOST, port: int = BEEFWEB_PORT) -> BeefWebBridge:
    """Return the module-level BeefWeb bridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = BeefWebBridge(host=host, port=port)
    return _bridge_instance


def _generate_session_id() -> str:
    """Generate a short session identifier for logging grouping."""
    import hashlib
    ts = str(time.time()).encode()
    return hashlib.sha1(ts).hexdigest()[:8]
