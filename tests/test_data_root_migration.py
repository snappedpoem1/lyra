from __future__ import annotations

import json
from pathlib import Path

import oracle.config as config
import oracle.data_root_migration as migration


def _configure_paths(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    project_root = tmp_path / "project"
    data_root = tmp_path / "LocalAppData" / "Lyra" / "dev"
    build_root = tmp_path / ".lyra-build"

    legacy_db = project_root / "lyra_registry.db"
    legacy_chroma = project_root / "chroma_storage"
    legacy_downloads = project_root / "downloads"
    legacy_staging = project_root / "staging"
    legacy_reports = project_root / "Reports"
    legacy_playlists = project_root / "playlists"
    legacy_vibes = project_root / "Vibes"
    legacy_spotify = project_root / "data" / "spotify"
    legacy_logs = project_root / "logs"
    legacy_tmp = project_root / "tmp"
    legacy_state = project_root / "state"
    legacy_cache = project_root / "hf_cache"

    targets = {
        "project_root": project_root,
        "data_root": data_root,
        "build_root": build_root,
        "legacy_db": legacy_db,
        "legacy_chroma": legacy_chroma,
        "legacy_profile": project_root / ".lyra_profile",
        "legacy_pause": project_root / ".lyra_paused",
        "db_path": data_root / "db" / "lyra_registry.db",
        "chroma_path": data_root / "chroma",
        "downloads": data_root / "downloads",
        "staging": data_root / "staging",
        "reports": data_root / "Reports",
        "playlists": data_root / "playlists",
        "vibes": data_root / "Vibes",
        "spotify_data": data_root / "data" / "spotify",
        "logs": data_root / "logs",
        "tmp": data_root / "tmp",
        "state": data_root / "state",
        "cache": data_root / "cache" / "hf",
    }

    project_root.mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(config, "DATA_ROOT", data_root)
    monkeypatch.setattr(config, "BUILD_ROOT", build_root)
    monkeypatch.setattr(config, "LEGACY_DB_PATH", legacy_db)
    monkeypatch.setattr(config, "LEGACY_CHROMA_PATH", legacy_chroma)
    monkeypatch.setattr(config, "LEGACY_DOWNLOADS_FOLDER", legacy_downloads)
    monkeypatch.setattr(config, "LEGACY_STAGING_FOLDER", legacy_staging)
    monkeypatch.setattr(config, "LEGACY_REPORTS_FOLDER", legacy_reports)
    monkeypatch.setattr(config, "LEGACY_PLAYLISTS_FOLDER", legacy_playlists)
    monkeypatch.setattr(config, "LEGACY_VIBES_FOLDER", legacy_vibes)
    monkeypatch.setattr(config, "LEGACY_SPOTIFY_DATA_DIR", legacy_spotify)
    monkeypatch.setattr(config, "LEGACY_LOG_ROOT", legacy_logs)
    monkeypatch.setattr(config, "LEGACY_TEMP_ROOT", legacy_tmp)
    monkeypatch.setattr(config, "LEGACY_STATE_ROOT", legacy_state)
    monkeypatch.setattr(config, "LEGACY_MODEL_CACHE_ROOT", legacy_cache)
    monkeypatch.setattr(config, "LYRA_DB_PATH", targets["db_path"])
    monkeypatch.setattr(config, "CHROMA_PATH", targets["chroma_path"])
    monkeypatch.setattr(config, "DOWNLOADS_FOLDER", targets["downloads"])
    monkeypatch.setattr(config, "STAGING_FOLDER", targets["staging"])
    monkeypatch.setattr(config, "REPORTS_FOLDER", targets["reports"])
    monkeypatch.setattr(config, "PLAYLISTS_FOLDER", targets["playlists"])
    monkeypatch.setattr(config, "VIBES_FOLDER", targets["vibes"])
    monkeypatch.setattr(config, "SPOTIFY_DATA_DIR", targets["spotify_data"])
    monkeypatch.setattr(config, "LOG_ROOT", targets["logs"])
    monkeypatch.setattr(config, "TEMP_ROOT", targets["tmp"])
    monkeypatch.setattr(config, "STATE_ROOT", targets["state"])
    monkeypatch.setattr(config, "MODEL_CACHE_ROOT", targets["cache"])
    monkeypatch.setattr(config, "MODEL_CACHE_HUB_ROOT", targets["cache"] / "hub")
    monkeypatch.setattr(config, "legacy_data_override_allowed", lambda: False)
    monkeypatch.setattr(config, "ensure_generated_dirs", lambda: [path.mkdir(parents=True, exist_ok=True) for path in [
        data_root,
        build_root,
        targets["db_path"].parent,
        targets["chroma_path"],
        targets["downloads"],
        targets["staging"],
        targets["reports"],
        targets["playlists"],
        targets["vibes"],
        targets["spotify_data"],
        targets["logs"],
        targets["tmp"],
        targets["state"],
        targets["cache"],
        targets["cache"] / "hub",
    ]])
    return targets


def test_build_data_root_report_surfaces_required_actions(monkeypatch, tmp_path: Path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    paths["legacy_db"].write_text("legacy-db", encoding="utf-8")
    paths["legacy_chroma"].mkdir(parents=True)
    (paths["legacy_chroma"] / "segment.bin").write_text("segment", encoding="utf-8")

    payload = migration.build_data_root_report()

    assert payload["migration_required"] is True
    assert "database" in payload["legacy_paths"]
    assert "python -m oracle.cli data-root migrate --yes" == payload["recommended_actions"]["migrate_now"]


def test_migrate_legacy_data_copies_runtime_state(monkeypatch, tmp_path: Path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    paths["legacy_db"].write_text("legacy-db", encoding="utf-8")
    paths["legacy_chroma"].mkdir(parents=True)
    (paths["legacy_chroma"] / "segment.bin").write_text("segment", encoding="utf-8")
    paths["legacy_profile"].write_text("performance", encoding="utf-8")
    paths["legacy_pause"].write_text(json.dumps({"paused": True}), encoding="utf-8")

    payload = migration.migrate_legacy_data()

    assert payload["failures"] == 0
    assert payload["migration_required"] is False
    assert paths["db_path"].read_text(encoding="utf-8") == "legacy-db"
    assert (paths["chroma_path"] / "segment.bin").read_text(encoding="utf-8") == "segment"
    assert (paths["state"] / "profile").read_text(encoding="utf-8") == "performance"
    assert json.loads((paths["state"] / "pause.json").read_text(encoding="utf-8"))["paused"] is True


def test_get_defer_payload_requires_explicit_override() -> None:
    payload = migration.get_defer_payload()

    assert payload["env_var"] == "LYRA_USE_LEGACY_DATA_ROOT"
    assert payload["value"] == "1"
    assert "Temporary fallback only" in payload["note"]
