from __future__ import annotations

from pathlib import Path

import oracle.bootstrap as bootstrap
import oracle.config as config
from oracle.runtime_services import get_packaging_summary, get_runtime_service_manifest


def test_find_bundled_tool_prefers_runtime_dirs(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    bin_dir = runtime_root / "bin"
    bin_dir.mkdir(parents=True)
    bundled = bin_dir / "spotdl.exe"
    bundled.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(config, "RUNTIME_ROOT", runtime_root)

    found = config.find_bundled_tool("spotdl.exe", "spotdl")
    assert found == str(bundled)


def test_resolve_project_root_prefers_frozen_executable(monkeypatch, tmp_path: Path) -> None:
    frozen_root = tmp_path / "installed"
    executable = frozen_root / "lyra_backend.exe"
    frozen_root.mkdir(parents=True)
    executable.write_text("stub", encoding="utf-8")

    monkeypatch.delenv("LYRA_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(executable))

    assert config._resolve_project_root() == frozen_root


def test_ensure_generated_dirs_creates_expected_roots(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "Lyra" / "dev"
    build_root = tmp_path / ".lyra-build"
    db_path = data_root / "db" / "lyra_registry.db"
    chroma_root = data_root / "chroma"
    downloads_root = data_root / "downloads"
    staging_root = data_root / "staging"
    reports_root = data_root / "Reports"
    playlists_root = data_root / "playlists"
    vibes_root = data_root / "Vibes"
    spotify_root = data_root / "data" / "spotify"
    state_root = build_root / "state"
    log_root = build_root / "logs"
    temp_root = build_root / "tmp"
    cache_root = build_root / "cache" / "hf"
    cache_hub_root = cache_root / "hub"

    monkeypatch.setattr(config, "DATA_ROOT", data_root)
    monkeypatch.setattr(config, "BUILD_ROOT", build_root)
    monkeypatch.setattr(config, "LYRA_DB_PATH", db_path)
    monkeypatch.setattr(config, "CHROMA_PATH", chroma_root)
    monkeypatch.setattr(config, "DOWNLOADS_FOLDER", downloads_root)
    monkeypatch.setattr(config, "STAGING_FOLDER", staging_root)
    monkeypatch.setattr(config, "REPORTS_FOLDER", reports_root)
    monkeypatch.setattr(config, "PLAYLISTS_FOLDER", playlists_root)
    monkeypatch.setattr(config, "VIBES_FOLDER", vibes_root)
    monkeypatch.setattr(config, "SPOTIFY_DATA_DIR", spotify_root)
    monkeypatch.setattr(config, "STATE_ROOT", state_root)
    monkeypatch.setattr(config, "LOG_ROOT", log_root)
    monkeypatch.setattr(config, "TEMP_ROOT", temp_root)
    monkeypatch.setattr(config, "MODEL_CACHE_ROOT", cache_root)
    monkeypatch.setattr(config, "MODEL_CACHE_HUB_ROOT", cache_hub_root)

    config.ensure_generated_dirs()

    assert data_root.exists()
    assert build_root.exists()
    assert db_path.parent.exists()
    assert chroma_root.exists()
    assert downloads_root.exists()
    assert staging_root.exists()
    assert reports_root.exists()
    assert playlists_root.exists()
    assert vibes_root.exists()
    assert spotify_root.exists()
    assert state_root.exists()
    assert log_root.exists()
    assert temp_root.exists()
    assert cache_root.exists()
    assert cache_hub_root.exists()


def test_bootstrap_runtime_skips_legacy_services_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LYRA_BOOTSTRAP_LEGACY_SERVICES", raising=False)
    monkeypatch.setattr(
        bootstrap,
        "ensure_lmstudio",
        lambda timeout_seconds=30: {"ready": True, "started": False, "timeout_seconds": timeout_seconds},
    )

    payload = bootstrap.bootstrap_runtime(timeout_seconds=12)

    assert payload["external_services"]["skipped"] is True
    assert payload["external_services"]["legacy_layer"] is True
    assert payload["llm"]["ready"] is True


def test_runtime_service_manifest_marks_docker_optional() -> None:
    manifest = get_runtime_service_manifest()
    summary = get_packaging_summary()

    assert manifest["docker"]["required_for_core_app"] is False
    assert manifest["docker"]["packaging_mode"] == "optional_legacy_layer"
    assert "streamrip" in summary["bundle_now"]
    assert "slskd" in summary["optional_external"]
