"""Auth rib — token-based request authentication for the Flask application.

Isolating the auth concern means a misconfigured token or a future auth
change (e.g. JWT, session) touches exactly one file.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, Response, g, jsonify, request

logger = logging.getLogger(__name__)


def init_auth(app: Flask) -> None:
    """Attach a ``before_request`` hook that enforces bearer-token auth.

    When ``LYRA_API_TOKEN`` is empty or absent the API runs in open mode —
    every request is treated as authenticated.  Set the variable to enforce
    token checks on all ``/api/*`` routes except ``/api/health``.

    Args:
        app: The Flask application instance.
    """
    if not os.getenv("LYRA_API_TOKEN", "").strip():
        logger.debug("[auth] LYRA_API_TOKEN not set — running in open mode")

    @app.before_request
    def require_api_token() -> Response | None:
        # Re-read each request so tests can monkeypatch os.environ.
        api_token = os.getenv("LYRA_API_TOKEN", "").strip()
        if not request.path.startswith("/api/"):
            return None
        if request.path == "/api/health":
            return None
        g.authenticated = not api_token
        if not api_token:
            return None
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header != f"Bearer {api_token}":
            return jsonify({"error": "Unauthorized", "status": 401}), 401  # type: ignore[return-value]
        g.authenticated = True
        return None
