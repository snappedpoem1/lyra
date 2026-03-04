"""Optional local musicnn tag inference provider."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("MUSICNN_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
_MODEL = os.getenv("MUSICNN_MODEL", "MSD_musicnn").strip() or "MSD_musicnn"


def is_enabled() -> bool:
    return _ENABLED


def build_track_profile(filepath: str, top_k: int = 8) -> Dict[str, Any]:
    """Infer semantic tags with musicnn if enabled and installed.

    Returns empty dict when disabled/unavailable so callers can fail-soft.
    """
    if not _ENABLED:
        return {}

    path = Path(filepath)
    if not path.exists():
        return {}

    try:
        import numpy as np
        from musicnn.extractor import extractor
    except Exception as exc:
        logger.debug("musicnn unavailable: %s", exc)
        return {}

    try:
        taggram, tags, _ = extractor(str(path), model=_MODEL, extract_features=False)
        if taggram is None or not len(taggram):
            return {}
        mean_scores = np.mean(taggram, axis=0)
        scored: List[tuple[str, float]] = []
        for idx, tag in enumerate(tags):
            try:
                scored.append((str(tag), float(mean_scores[idx])))
            except Exception:
                continue
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: max(1, int(top_k))]
        return {
            "provider": "musicnn",
            "model": _MODEL,
            "filepath": str(path),
            "top_tags": [name for name, _ in top],
            "tag_scores": [{"tag": name, "score": score} for name, score in top],
        }
    except Exception as exc:
        logger.debug("musicnn inference failed for %s: %s", path, exc)
        return {}

