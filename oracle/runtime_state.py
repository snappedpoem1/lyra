"""Runtime controls for performance profile and pause/resume."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

from oracle.config import PROJECT_ROOT, STATE_ROOT, ensure_generated_dirs

logger = logging.getLogger(__name__)

_PROFILE_FILE = Path(STATE_ROOT) / "profile"
_PROFILE_FILE_LEGACY = Path(PROJECT_ROOT) / ".lyra_profile"
_PAUSE_FILE = Path(STATE_ROOT) / "pause.json"
_PAUSE_FILE_LEGACY = Path(PROJECT_ROOT) / ".lyra_paused"
_VALID_PROFILES = {"balanced", "performance", "quiet"}


def _read_text(*paths: Path) -> Optional[str]:
    for path in paths:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            continue
    return None


def get_profile(default: str = "balanced") -> str:
    try:
        payload = _read_text(_PROFILE_FILE, _PROFILE_FILE_LEGACY)
        if payload is not None:
            value = payload.strip().lower()
            if value in _VALID_PROFILES:
                return value
    except Exception:
        pass
    return default


def set_profile(profile: str) -> str:
    value = (profile or "").strip().lower()
    if value not in _VALID_PROFILES:
        raise ValueError(f"Invalid profile: {profile}. Use one of: {', '.join(sorted(_VALID_PROFILES))}")
    ensure_generated_dirs()
    _PROFILE_FILE.write_text(value, encoding="utf-8")
    return value


def pause(reason: str = "") -> None:
    ensure_generated_dirs()
    payload = {
        "paused": True,
        "reason": (reason or "").strip(),
        "timestamp": time.time(),
    }
    _PAUSE_FILE.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def resume() -> None:
    for path in (_PAUSE_FILE, _PAUSE_FILE_LEGACY):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def is_paused() -> Tuple[bool, Optional[str]]:
    raw_payload = _read_text(_PAUSE_FILE, _PAUSE_FILE_LEGACY)
    if raw_payload is None:
        return False, None
    try:
        payload = json.loads(raw_payload)
        reason = str(payload.get("reason", "")).strip() or None
        return True, reason
    except Exception:
        return True, None


def wait_if_paused(label: str = "task", poll_seconds: float = 2.0) -> None:
    announced = False
    while True:
        paused, reason = is_paused()
        if not paused:
            if announced:
                logger.info("[pause] Resuming %s.", label)
            return
        if not announced:
            msg = f"[pause] {label} paused"
            if reason:
                msg += f" ({reason})"
            msg += ". Waiting..."
            logger.info(msg)
            announced = True
        time.sleep(max(0.2, float(poll_seconds)))

