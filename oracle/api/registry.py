"""Blueprint registry rib — manifest and fault-tolerant registration.

**Adding a new blueprint:** append its module path and optional ``url_prefix``
to ``BLUEPRINTS``.  No other file needs to change.

**Resilience:** each blueprint is imported and registered inside a ``try``
block.  A broken blueprint emits a logged warning and is skipped — the rest
of the API keeps running.  This means a syntax error in ``radio.py`` will not
take down search, library, or vibes.
"""

from __future__ import annotations

import importlib
import logging
from typing import NamedTuple

from flask import Flask

logger = logging.getLogger(__name__)


class BlueprintSpec(NamedTuple):
    """Describes a single blueprint to register."""

    module: str
    """Fully-qualified module path, e.g. ``oracle.api.blueprints.search``."""

    bp_attr: str = "bp"
    """Name of the ``Blueprint`` object inside the module (default ``bp``)."""


# ── Manifest ──────────────────────────────────────────────────────────────
# Order determines registration order, which affects route resolution when
# two blueprints share a prefix.  Core first, heaviest modules last.
BLUEPRINTS: list[BlueprintSpec] = [
    BlueprintSpec("oracle.api.blueprints.core"),
    BlueprintSpec("oracle.api.blueprints.search"),
    BlueprintSpec("oracle.api.blueprints.library"),
    BlueprintSpec("oracle.api.blueprints.player"),
    BlueprintSpec("oracle.api.blueprints.oracle_actions"),
    BlueprintSpec("oracle.api.blueprints.recommendations"),
    BlueprintSpec("oracle.api.blueprints.vibes"),
    BlueprintSpec("oracle.api.blueprints.acquire"),
    BlueprintSpec("oracle.api.blueprints.intelligence"),
    BlueprintSpec("oracle.api.blueprints.radio"),
    BlueprintSpec("oracle.api.blueprints.agent"),
    BlueprintSpec("oracle.api.blueprints.pipeline"),
    BlueprintSpec("oracle.api.blueprints.enrich"),
    BlueprintSpec("oracle.api.blueprints.discovery"),
]


def register_blueprints(app: Flask) -> None:
    """Import and register every blueprint listed in ``BLUEPRINTS``.

    Failed blueprints are logged and skipped; the rest of the API continues
    to function.

    Args:
        app: The Flask application instance.
    """
    registered = 0
    failed: list[str] = []

    for spec in BLUEPRINTS:
        try:
            module = importlib.import_module(spec.module)
            bp = getattr(module, spec.bp_attr)
            app.register_blueprint(bp)
            registered += 1
            logger.debug("[registry] registered %s", spec.module)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[registry] DEGRADED — could not load blueprint %s: %s",
                spec.module,
                exc,
                exc_info=True,
            )
            failed.append(spec.module)

    if failed:
        logger.warning(
            "[registry] %d blueprint(s) failed to load: %s",
            len(failed),
            ", ".join(failed),
        )
    logger.info("[registry] %d/%d blueprints registered", registered, len(BLUEPRINTS))
