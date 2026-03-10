"""Oracle API package — spine.

Re-exports the public interface so existing import paths keep working::

    from oracle.api import create_app   # WSGI / gunicorn
    from oracle.api import main         # direct run

All logic lives in the dedicated rib modules:

  oracle.api.app        — Flask application factory + CLI entry-point
  oracle.api.cors       — CORS initialisation
  oracle.api.auth       — bearer-token request authentication
  oracle.api.registry   — fault-tolerant blueprint registration
  oracle.api.scheduler  — embedded APScheduler (BackgroundScheduler)
  oracle.api.blueprints — route handlers (11 independent ribs)
"""

from oracle.api.app import VERSION, create_app, main

__all__ = ["VERSION", "create_app", "main"]
