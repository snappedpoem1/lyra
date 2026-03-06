"""
oracle.config â€” Configuration Management

Loads .env, validates API credentials, resolves paths.
Every other module imports from here.
"""

import os
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from oracle.llm_config import load_llm_config, resolve_llm_config


# â”€â”€ Resolve project root (wherever start.py lives) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _resolve_project_root() -> Path:
    env_root = os.environ.get("LYRA_PROJECT_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()

if load_dotenv:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        # Preserve explicit runtime env vars set by callers/tests.
        load_dotenv(env_file, override=False)


def _env_path(key: str, fallback: Path) -> Path:
    value = os.environ.get(key, "").strip()
    return Path(value) if value else fallback


LYRA_DB_PATH = _env_path("LYRA_DB_PATH", PROJECT_ROOT / "lyra_registry.db")
CHROMA_PATH = _env_path("CHROMA_PATH", _env_path("CHROMA_DIR", PROJECT_ROOT / "chroma_storage"))
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "clap_embeddings").strip() or "clap_embeddings"
LIBRARY_BASE = _env_path("LIBRARY_BASE", _env_path("LIBRARY_DIR", PROJECT_ROOT / "library"))
DOWNLOADS_FOLDER = _env_path("DOWNLOADS_FOLDER", _env_path("DOWNLOAD_DIR", PROJECT_ROOT / "downloads"))
STAGING_FOLDER = _env_path("STAGING_FOLDER", _env_path("STAGING_DIR", PROJECT_ROOT / "staging"))
QUARANTINE_PATH = _env_path("QUARANTINE_PATH", LIBRARY_BASE.parent / "_Quarantine")
REJECTED_FOLDER = _env_path("REJECTED_FOLDER", LIBRARY_BASE.parent / "_Rejected")
VIBES_FOLDER = _env_path("VIBES_FOLDER", PROJECT_ROOT / "Vibes")
REPORTS_FOLDER = _env_path("REPORTS_FOLDER", PROJECT_ROOT / "Reports")
PLAYLISTS_FOLDER = _env_path("PLAYLISTS_FOLDER", PROJECT_ROOT / "playlists")
ACOUSTID_API_KEY = os.environ.get("ACOUSTID_API_KEY", "").strip()
FPCALC_PATH = os.environ.get("FPCALC_PATH", "").strip()
RUNTIME_ROOT = _env_path("LYRA_RUNTIME_ROOT", PROJECT_ROOT / "runtime")


def guard_bypass_allowed() -> bool:
    """Return True only when guard bypass is explicitly allowed."""
    value = os.environ.get("LYRA_ALLOW_GUARD_BYPASS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def guard_bypass_reason() -> str:
    """Human-readable reason used for guard bypass audit logging."""
    reason = os.environ.get("LYRA_GUARD_BYPASS_REASON", "").strip()
    return reason or "unspecified"


def get_llm_settings() -> dict:
    """Return LLM settings from environment."""
    config = resolve_llm_config(load_llm_config(resolve_endpoint=False))
    settings = config.masked_summary()
    settings["provider"] = config.provider_type
    settings["api_key"] = config.api_key
    settings["fallback_model"] = config.fallback_model
    settings["timeout_seconds"] = config.timeout_seconds
    return settings


def get_runtime_bin_dirs() -> list[Path]:
    """Return candidate directories for bundled runtime executables."""
    runtime_root = Path(RUNTIME_ROOT)
    return [
        runtime_root / "bin",
        runtime_root / "tools",
        runtime_root / "acquisition-tools",
    ]


def find_bundled_tool(*names: str) -> Optional[str]:
    """Find a bundled executable or script in Lyra's runtime directories."""
    for base_dir in get_runtime_bin_dirs():
        for name in names:
            candidate = base_dir / name
            if candidate.exists():
                return str(candidate)
    return None


def validate_required_env(required_keys: list[str]) -> None:
    """Raise when any required environment key is missing/blank."""
    missing = [key for key in required_keys if not os.environ.get(key, "").strip()]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required environment keys: {joined}")


def get_connection(timeout: float = 10.0):
    """Delegate to oracle.db.schema.get_connection (single source of truth + WAL pragmas)."""
    from oracle.db.schema import get_connection as _get_connection
    return _get_connection(timeout=timeout)


@dataclass
class OracleConfig:
    """Centralized configuration for the entire Music Oracle system."""

    # API Keys
    genius_token: str = ""
    lastfm_api_key: str = ""
    lastfm_api_secret: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # Prowlarr indexer
    prowlarr_url: str = "http://localhost:9696"
    prowlarr_api_key: str = ""

    # Real-Debrid
    real_debrid_key: str = ""

    # Rclone
    rclone_remote: str = "lyra_remote"
    rclone_mount_drive: str = "L:"

    # ChromaDB (sonic DNA)
    chroma_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "chroma_storage")
    chroma_collection: str = "clap_embeddings"

    # Paths
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    download_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "downloads")
    staging_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "staging")
    library_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "library")
    spotify_data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "spotify")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    db_path: Path = field(default_factory=lambda: LYRA_DB_PATH)

    # Download prefs
    preferred_codec: str = "m4a"
    preferred_quality: str = "256"
    sleep_min: int = 5
    sleep_max: int = 15

    @property
    def has_genius(self) -> bool:
        return bool(self.genius_token)

    @property
    def has_lastfm(self) -> bool:
        return bool(self.lastfm_api_key)

    @property
    def has_spotify_creds(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    @property
    def has_prowlarr(self) -> bool:
        return bool(self.prowlarr_api_key)

    @property
    def has_real_debrid(self) -> bool:
        return bool(self.real_debrid_key)

    def api_status(self) -> dict:
        """Return a dict of which APIs are configured."""
        return {
            "Genius (lyrics/metadata)": self.has_genius,
            "Last.fm (artist intel)": self.has_lastfm,
            "Spotify (live sync)": self.has_spotify_creds,
            "Prowlarr (indexer)": self.has_prowlarr,
            "Real-Debrid (premium)": self.has_real_debrid,
        }

    def tool_status(self) -> dict:
        """Check which system tools are available on PATH."""
        def check_yt_dlp():
            # First try the command-line tool
            if shutil.which("yt-dlp") is not None:
                return True
            # Fall back to checking if the Python module is available
            try:
                __import__("yt_dlp")
                return True
            except ImportError:
                return False
        
        return {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "rclone": shutil.which("rclone") is not None,
            "yt-dlp": check_yt_dlp(),
        }

    def ensure_dirs(self):
        """Create all required directories."""
        for d in [self.download_dir, self.staging_dir, self.library_dir,
                  self.spotify_data_dir, self.log_dir, self.db_path.parent,
                  self.chroma_dir, REPORTS_FOLDER, PLAYLISTS_FOLDER, VIBES_FOLDER]:
            d.mkdir(parents=True, exist_ok=True)


def load_config(env_path: Optional[Path] = None) -> OracleConfig:
    """Load configuration from .env file + environment variables."""

    # Try loading .env
    env_file = env_path or PROJECT_ROOT / ".env"
    if load_dotenv and env_file.exists():
        # Respect process env as source-of-truth when explicitly provided.
        load_dotenv(env_file, override=False)
    elif not env_file.exists():
        # Copy a sanitized example if available; never auto-materialize from
        # local-only templates that may contain machine-specific secrets.
        example_template = PROJECT_ROOT / ".env.example"
        legacy_template = PROJECT_ROOT / ".env.template"

        # Prefer the new .env.example when present, but fall back to the
        # legacy .env.template for backward compatibility.
        source_template = None
        if example_template.exists():
            source_template = example_template
        elif legacy_template.exists():
            source_template = legacy_template

        if source_template is not None:
            shutil.copy2(source_template, env_file)
            if load_dotenv:
                load_dotenv(env_file, override=False)

    def _env(key: str, default: str = "") -> str:
        return os.environ.get(key, default).strip()

    def _env_int(key: str, default: int = 0) -> int:
        val = os.environ.get(key, "")
        return int(val) if val.strip().isdigit() else default

    cfg = OracleConfig(
        genius_token=_env("GENIUS_TOKEN") or _env("GENIUS_ACCESS_TOKEN"),
        lastfm_api_key=_env("LASTFM_API_KEY"),
        lastfm_api_secret=_env("LASTFM_API_SECRET"),
        spotify_client_id=_env("SPOTIFY_CLIENT_ID"),
        spotify_client_secret=_env("SPOTIFY_CLIENT_SECRET"),
        prowlarr_url=_env("PROWLARR_URL", "http://localhost:9696"),
        prowlarr_api_key=_env("PROWLARR_API_KEY"),
        real_debrid_key=_env("REAL_DEBRID_KEY"),
        rclone_remote=_env("RCLONE_REMOTE_NAME", "lyra_remote"),
        rclone_mount_drive=_env("RCLONE_MOUNT_DRIVE", "L:"),
        preferred_codec=_env("PREFERRED_CODEC", "m4a"),
        preferred_quality=_env("PREFERRED_QUALITY", "256"),
        sleep_min=_env_int("SLEEP_MIN", 5),
        sleep_max=_env_int("SLEEP_MAX", 15),
    )

    # Override paths if set in env (check both legacy and current var names)
    dl_dir = _env("DOWNLOADS_FOLDER") or _env("DOWNLOAD_DIR")
    if dl_dir:
        cfg.download_dir = Path(dl_dir)
    lib_dir = _env("LIBRARY_BASE") or _env("LIBRARY_DIR")
    if lib_dir:
        cfg.library_dir = Path(lib_dir)
    if _env("SPOTIFY_DATA_DIR"):
        cfg.spotify_data_dir = Path(_env("SPOTIFY_DATA_DIR"))
    chroma_dir = _env("CHROMA_PATH") or _env("CHROMA_DIR")
    if chroma_dir:
        cfg.chroma_dir = Path(chroma_dir)
    if _env("CHROMA_COLLECTION"):
        cfg.chroma_collection = _env("CHROMA_COLLECTION")

    cfg.ensure_dirs()
    return cfg
