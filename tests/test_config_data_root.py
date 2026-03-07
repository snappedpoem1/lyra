from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SCRIPT = """
from __future__ import annotations

import json
import os
import sys

if os.environ.get("LYRA_TEST_FROZEN", "").strip().lower() in {"1", "true", "yes", "on"}:
    setattr(sys, "frozen", True)
    executable = os.environ.get("LYRA_TEST_EXECUTABLE", "").strip()
    if executable:
        setattr(sys, "executable", executable)

import oracle.config as config

payload = {
    "project_root": str(config.PROJECT_ROOT),
    "data_root": str(config.DATA_ROOT),
    "db_path": str(config.LYRA_DB_PATH),
    "chroma_path": str(config.CHROMA_PATH),
    "log_root": str(config.LOG_ROOT),
    "temp_root": str(config.TEMP_ROOT),
    "state_root": str(config.STATE_ROOT),
    "model_cache_root": str(config.MODEL_CACHE_ROOT),
    "build_root": str(config.BUILD_ROOT),
    "legacy_override": config.legacy_data_override_allowed(),
    "legacy_paths": sorted(config.detect_legacy_data_paths().keys()),
    "migration_required": config.legacy_data_migration_required(),
}
print(json.dumps(payload))
"""


def _probe_config(**env_overrides: str) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    for key in [
        "LYRA_DATA_ROOT",
        "LYRA_DB_PATH",
        "CHROMA_PATH",
        "CHROMA_DIR",
        "LYRA_BUILD_ROOT",
        "LYRA_LOG_ROOT",
        "LYRA_TEMP_ROOT",
        "LYRA_STATE_ROOT",
        "LYRA_MODEL_CACHE_ROOT",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
        "LYRA_USE_LEGACY_DATA_ROOT",
        "LYRA_TEST_FROZEN",
        "LYRA_TEST_EXECUTABLE",
        "LYRA_PROJECT_ROOT",
    ]:
        env.pop(key, None)
    env.update(env_overrides)
    completed = subprocess.run(
        [sys.executable, "-c", PROBE_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_config_defaults_to_dev_data_root(tmp_path: Path) -> None:
    local_appdata = tmp_path / "LocalAppData"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    payload = _probe_config(
        LOCALAPPDATA=str(local_appdata),
        LYRA_PROJECT_ROOT=str(project_root),
    )

    expected_root = local_appdata / "Lyra" / "dev"
    assert Path(str(payload["data_root"])) == expected_root
    assert Path(str(payload["db_path"])) == expected_root / "db" / "lyra_registry.db"
    assert Path(str(payload["chroma_path"])) == expected_root / "chroma"
    assert Path(str(payload["log_root"])) == expected_root / "logs"
    assert Path(str(payload["temp_root"])) == expected_root / "tmp"
    assert Path(str(payload["state_root"])) == expected_root / "state"
    assert Path(str(payload["model_cache_root"])) == expected_root / "cache" / "hf"


def test_config_defaults_to_installed_data_root_when_frozen(tmp_path: Path) -> None:
    local_appdata = tmp_path / "LocalAppData"
    installed_root = tmp_path / "installed"
    executable = installed_root / "lyra_backend.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("stub", encoding="utf-8")

    payload = _probe_config(
        LOCALAPPDATA=str(local_appdata),
        LYRA_TEST_FROZEN="1",
        LYRA_TEST_EXECUTABLE=str(executable),
    )

    assert Path(str(payload["project_root"])) == installed_root
    assert Path(str(payload["data_root"])) == local_appdata / "Lyra"


def test_config_detects_legacy_state_until_new_data_root_has_state(tmp_path: Path) -> None:
    local_appdata = tmp_path / "LocalAppData"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "lyra_registry.db").write_text("legacy", encoding="utf-8")
    (project_root / "chroma_storage").mkdir(parents=True)

    payload = _probe_config(
        LOCALAPPDATA=str(local_appdata),
        LYRA_PROJECT_ROOT=str(project_root),
    )

    assert payload["legacy_override"] is False
    assert payload["migration_required"] is True
    assert set(payload["legacy_paths"]) >= {"database", "chroma"}

    data_root = local_appdata / "Lyra" / "dev"
    db_root = data_root / "db"
    db_root.mkdir(parents=True)
    (db_root / "lyra_registry.db").write_text("new", encoding="utf-8")

    payload_after_seed = _probe_config(
        LOCALAPPDATA=str(local_appdata),
        LYRA_PROJECT_ROOT=str(project_root),
    )

    assert payload_after_seed["migration_required"] is False


def test_config_legacy_override_routes_mutable_paths_to_project_root(tmp_path: Path) -> None:
    local_appdata = tmp_path / "LocalAppData"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    payload = _probe_config(
        LOCALAPPDATA=str(local_appdata),
        LYRA_PROJECT_ROOT=str(project_root),
        LYRA_USE_LEGACY_DATA_ROOT="1",
    )

    assert payload["legacy_override"] is True
    assert Path(str(payload["data_root"])) == local_appdata / "Lyra" / "dev"
    assert Path(str(payload["db_path"])) == project_root / "lyra_registry.db"
    assert Path(str(payload["chroma_path"])) == project_root / "chroma_storage"
    assert Path(str(payload["log_root"])) == project_root / "logs"
    assert Path(str(payload["temp_root"])) == project_root / "tmp"
    assert Path(str(payload["state_root"])) == project_root / "state"
    assert Path(str(payload["model_cache_root"])) == project_root / "hf_cache"
