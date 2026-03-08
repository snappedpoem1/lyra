"""CORS rib — isolated CORS initialisation for the Flask application.

Changing allowed origins never requires touching the app factory.
Origin list is driven by the ``CORS_ALLOWED_ORIGINS`` env variable.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, request as flask_request

try:
    from flask_cors import CORS as _FlaskCORS
except ImportError:
    _FlaskCORS = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
    "app://localhost",
    "null",
)


def _resolve_origins() -> list[str] | str:
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        ",".join(DEFAULT_ALLOWED_ORIGINS),
    )
    origins: list[str] | str = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins or origins == ["*"]:
        return "*"
    return origins


def _make_fallback_cors_handler(origins: list[str] | str):
    """Return an after_request handler that guarantees CORS headers.

    Acts as a safety net for packaged/frozen builds where flask_cors may
    not initialise its middleware correctly.
    """
    allow_all = origins == "*"
    origin_set = set(origins) if isinstance(origins, list) else set()

    def _ensure_cors(response):
        if "Access-Control-Allow-Origin" in response.headers:
            return response  # flask_cors already handled it
        req_origin = flask_request.headers.get("Origin", "")
        if allow_all or req_origin in origin_set:
            response.headers["Access-Control-Allow-Origin"] = req_origin or "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "86400"
        return response

    return _ensure_cors


def init_cors(app: Flask) -> None:
    """Register CORS rules on *app*.

    Reads ``CORS_ALLOWED_ORIGINS`` (comma-separated).  Falls back to the
    standard dev origins when the variable is absent.  Passing ``"*"`` as
    the sole entry allows all origins.

    A manual ``after_request`` fallback is always registered so CORS headers
    are guaranteed even when ``flask_cors`` fails to apply (e.g. in frozen
    PyInstaller builds).

    Args:
        app: The Flask application instance.
    """
    origins = _resolve_origins()
    if _FlaskCORS is not None:
        try:
            _FlaskCORS(
                app,
                resources={
                    r"/api/*": {"origins": origins},
                    r"/ws/*": {"origins": origins},
                },
            )
        except Exception:
            logger.warning("flask_cors initialisation failed; relying on manual fallback", exc_info=True)
    else:
        logger.warning("flask_cors not available; using manual CORS handler")

    # Always register fallback — it is a no-op when flask_cors already set
    # the header, but guarantees CORS in packaged/frozen environments.
    app.after_request(_make_fallback_cors_handler(origins))
