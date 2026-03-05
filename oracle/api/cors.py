"""CORS rib — isolated CORS initialisation for the Flask application.

Changing allowed origins never requires touching the app factory.
Origin list is driven by the ``CORS_ALLOWED_ORIGINS`` env variable.
"""

from __future__ import annotations

import os

from flask import Flask
from flask_cors import CORS


def init_cors(app: Flask) -> None:
    """Register CORS rules on *app*.

    Reads ``CORS_ALLOWED_ORIGINS`` (comma-separated).  Falls back to the
    standard dev origins when the variable is absent.  Passing ``"*"`` as
    the sole entry allows all origins.

    Args:
        app: The Flask application instance.
    """
    raw = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,null",
    )
    origins: list[str] | str = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins or origins == ["*"]:
        origins = "*"
    CORS(app, resources={r"/api/*": {"origins": origins}})
