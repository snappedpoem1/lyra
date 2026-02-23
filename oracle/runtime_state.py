"""Runtime controls for performance profile and pause/resume."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Tuple

from oracle.config import PROJECT_ROOT

_PROFILE_FILE = Path(PROJECT_ROOT) / ".lyra_profile"
_PAUSE_FILE = Path(PROJECT_ROOT) / ".lyra_paused"
_VALID_PROFILES = {"balanced", "performance", "quiet"}


def get_profile(default: str = "balanced") -> str:
    try:
        if _PROFILE_FILE.exists():
            value = _PROFILE_FILE.read_text(encoding="utf-8").strip().lower()
            if value in _VALID_PROFILES:
                return value
    except Exception:
        pass
    return default


def set_profile(profile: str) -> str:
    value = (profile or "").strip().lower()
    if value not in _VALID_PROFILES:
        raise ValueError(f"Invalid profile: {profile}. Use one of: {', '.join(sorted(_VALID_PROFILES))}")
    _PROFILE_FILE.write_text(value, encoding="utf-8")
    return value


def pause(reason: str = "") -> None:
    payload = {
        "paused": True,
        "reason": (reason or "").strip(),
        "timestamp": time.time(),
    }
    _PAUSE_FILE.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def resume() -> None:
    try:
        _PAUSE_FILE.unlink()
    except FileNotFoundError:
        return


def is_paused() -> Tuple[bool, Optional[str]]:
    if not _PAUSE_FILE.exists():
        return False, None
    try:
        payload = json.loads(_PAUSE_FILE.read_text(encoding="utf-8"))
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
                print(f"[pause] Resuming {label}.")
            return
        if not announced:
            msg = f"[pause] {label} paused"
            if reason:
                msg += f" ({reason})"
            msg += ". Waiting..."
            print(msg)
            announced = True
        time.sleep(max(0.2, float(poll_seconds)))

