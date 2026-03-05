"""Streamrip acquisition backend - stub / not yet implemented.

Streamrip supports Qobuz, Tidal, Deezer, and SoundCloud downloads via a unified
CLI. This module is the intended T2 tier in the acquisition waterfall, sitting
between Qobuz (T1) and Slskd (T3).

Implementation notes:
    - streamrip must be installed separately and configured via
      ~/.config/streamrip/config.toml
    - Authentication tokens differ per service; no shared credential store yet
    - Integration requires subprocess calls to ``rip url ...`` or use of the
      streamrip Python API once it stabilizes

Until this is wired up ``is_available()`` returns ``False`` so the waterfall
skips cleanly to T3.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Return False - streamrip integration not yet implemented."""
    return False


def download(artist: str, title: str) -> Dict[str, Any]:
    """Attempt a streamrip download. Always fails until implemented.

    Args:
        artist: Artist name.
        title: Track title.

    Returns:
        Result dict with ``success=False`` and a descriptive error.
    """
    logger.debug("streamrip T2: not implemented - skipping %s / %s", artist, title)
    return {
        "success": False,
        "error": "streamrip tier not yet implemented",
        "tier": 2,
        "source": "streamrip",
    }
