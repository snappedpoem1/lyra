"""Performance tuning helpers for high-resource machines."""

from __future__ import annotations

import os

from oracle.runtime_state import get_profile


def cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def auto_workers(kind: str = "network") -> int:
    """Return a sensible worker count for a workload type."""
    cores = cpu_count()
    kind = (kind or "network").strip().lower()
    profile = get_profile("balanced")

    if profile == "performance":
        if kind == "network":
            return max(8, min(48, cores * 3))
        if kind == "io":
            return max(6, min(32, cores * 2))
        return max(4, min(24, cores))

    if profile == "quiet":
        if kind == "network":
            return max(2, min(8, cores // 2 or 2))
        if kind == "io":
            return max(2, min(6, cores // 2 or 2))
        return max(1, min(4, cores // 2 or 1))

    # balanced
    if kind == "network":
        return max(4, min(32, cores * 2))
    if kind == "io":
        return max(4, min(24, cores))
    return max(2, min(cores, 16))
