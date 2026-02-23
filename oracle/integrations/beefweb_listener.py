"""BeefWeb → Oracle playback bridge.

Subscribes to foobar2000's BeefWeb SSE event stream and forwards
play/skip/complete events to oracle's playback_history + taste system.

Requirements:
  - foobar2000 v2+ with foo_beefweb component installed
  - BeefWeb running on localhost:8880 (default)
  - pip install pyfoobeef

Usage:
    python -m oracle.integrations.beefweb_listener
    oracle listen  (via CLI)

BeefWeb install: https://www.foobar2000.org/components/view/foo_beefweb
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

BEEFWEB_HOST = "localhost"
BEEFWEB_PORT = 8880
RECONNECT_SECONDS = 3


def _resolve_track_id(artist: str, title: str) -> Optional[str]:
    """Look up track_id from oracle DB by artist+title."""
    try:
        from oracle.db.schema import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT track_id FROM tracks "
            "WHERE LOWER(artist) LIKE LOWER(?) AND LOWER(title) LIKE LOWER(?)",
            (f"%{artist}%", f"%{title}%"),
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as exc:
        logger.debug(f"[BeefWeb] DB lookup failed: {exc}")
        return None


def _record_play(track_id: str, skipped: bool, completion_rate: float) -> None:
    """Write to playback_history and update taste profile."""
    try:
        from oracle.db.schema import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO playback_history (track_id, ts, context, skipped, completion_rate)
               VALUES (?, ?, 'foobar2000', ?, ?)""",
            (track_id, time.time(), 1 if skipped else 0, completion_rate),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[BeefWeb] playback_history write failed: {exc}")

    try:
        from oracle.taste import update_taste_from_playback
        update_taste_from_playback(track_id, positive=not skipped)
    except Exception as exc:
        logger.warning(f"[BeefWeb] taste update failed: {exc}")


async def run_listener(
    host: str = BEEFWEB_HOST,
    port: int = BEEFWEB_PORT,
) -> None:
    """Subscribe to BeefWeb SSE and forward events to oracle.

    Tracks:
    - play: new track started (positive taste signal)
    - skip: track changed before ~50% duration (negative signal)
    - complete: track played ≥ 80% duration (strong positive signal)
    """
    try:
        import pyfoobeef
    except ImportError:
        logger.error("[BeefWeb] pyfoobeef not installed. Run: pip install pyfoobeef")
        return

    listener = pyfoobeef.EventListener(
        base_url=host,
        port=port,
        active_item_column_map={
            "%path%": "path",
            "%artist%": "artist",
            "%title%": "title",
            "%album%": "album",
            "%length_seconds%": "duration_seconds",
        },
    )

    # State tracking to detect skips vs completes
    prev_index: Optional[int] = None
    prev_playlist_id: Optional[str] = None
    track_started_at: float = 0.0
    current_duration: float = 0.0
    current_track_id: Optional[str] = None

    async def on_player_state(state: Any) -> None:
        nonlocal prev_index, prev_playlist_id, track_started_at
        nonlocal current_duration, current_track_id

        if not state:
            return

        item = state.active_item
        playback_state = state.playback_state  # "playing" | "paused" | "stopped"

        # Detect track change
        cur_index = item.index if item else None
        cur_playlist_id = item.playlist_id if item else None
        is_new_track = (
            cur_index != prev_index
            or cur_playlist_id != prev_playlist_id
        )

        if playback_state == "playing" and is_new_track and item:
            # A new track just started playing
            artist = item.columns.get("artist", "")
            title = item.columns.get("title", "")

            # Compute signal for the track that just ENDED (if any)
            if current_track_id and track_started_at > 0 and current_duration > 0:
                elapsed = time.time() - track_started_at
                completion_rate = min(1.0, elapsed / current_duration)
                skipped = completion_rate < 0.5
                signal = "SKIP" if skipped else "COMPLETE"
                logger.info(
                    f"[BeefWeb] {signal}: {completion_rate:.0%} "
                    f"played → track_id={current_track_id}"
                )
                _record_play(current_track_id, skipped=skipped,
                             completion_rate=completion_rate)

            # Start tracking the new track
            try:
                dur_str = item.columns.get("duration_seconds", "0")
                current_duration = float(dur_str) if dur_str else 0.0
            except (ValueError, TypeError):
                current_duration = 0.0

            track_started_at = time.time()
            new_track_id = _resolve_track_id(artist, title)
            current_track_id = new_track_id

            logger.info(
                f"[BeefWeb] NOW PLAYING: {artist} - {title} "
                f"(id={new_track_id or 'not in oracle'})"
            )

            prev_index = cur_index
            prev_playlist_id = cur_playlist_id

        elif playback_state == "stopped" and current_track_id:
            # Playback stopped — record as complete if we played most of it
            if track_started_at > 0 and current_duration > 0:
                elapsed = time.time() - track_started_at
                completion_rate = min(1.0, elapsed / current_duration)
                if completion_rate >= 0.8:
                    logger.info(
                        f"[BeefWeb] COMPLETE: {completion_rate:.0%} → id={current_track_id}"
                    )
                    _record_play(current_track_id, skipped=False,
                                 completion_rate=completion_rate)
            current_track_id = None
            track_started_at = 0.0

    listener.add_callback("player_state", on_player_state)

    logger.info(f"[BeefWeb] Connecting to foobar2000 at {host}:{port} ...")
    logger.info("[BeefWeb] Make sure foobar2000 + foo_beefweb are running.")
    logger.info("[BeefWeb] Ctrl+C to stop.\n")

    while True:
        try:
            await listener.connect(reconnect_time=RECONNECT_SECONDS)
            # Keep alive indefinitely
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("[BeefWeb] Stopped.")
            break
        except Exception as exc:
            logger.warning(f"[BeefWeb] Connection error: {exc}. Retrying in {RECONNECT_SECONDS}s...")
            await asyncio.sleep(RECONNECT_SECONDS)


def main() -> None:
    import argparse
    from dotenv import load_dotenv

    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="BeefWeb → Oracle playback bridge")
    parser.add_argument("--host", default=BEEFWEB_HOST, help="BeefWeb host (default: localhost)")
    parser.add_argument("--port", type=int, default=BEEFWEB_PORT, help="BeefWeb port (default: 8880)")
    args = parser.parse_args()

    asyncio.run(run_listener(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
