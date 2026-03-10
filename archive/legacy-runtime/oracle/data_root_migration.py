"""Safe migration helpers for the `LYRA_DATA_ROOT` cutover."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import shutil
from typing import Any

import oracle.config as config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationItem:
    """One legacy path that can be copied into the active data root."""

    label: str
    source: Path
    target: Path
    kind: str


def _iter_migration_items() -> list[MigrationItem]:
    return [
        MigrationItem("database", config.LEGACY_DB_PATH, config.LYRA_DB_PATH, "file"),
        MigrationItem("chroma", config.LEGACY_CHROMA_PATH, config.CHROMA_PATH, "directory"),
        MigrationItem("downloads", config.LEGACY_DOWNLOADS_FOLDER, config.DOWNLOADS_FOLDER, "directory"),
        MigrationItem("staging", config.LEGACY_STAGING_FOLDER, config.STAGING_FOLDER, "directory"),
        MigrationItem("reports", config.LEGACY_REPORTS_FOLDER, config.REPORTS_FOLDER, "directory"),
        MigrationItem("playlists", config.LEGACY_PLAYLISTS_FOLDER, config.PLAYLISTS_FOLDER, "directory"),
        MigrationItem("vibes", config.LEGACY_VIBES_FOLDER, config.VIBES_FOLDER, "directory"),
        MigrationItem("spotify_data", config.LEGACY_SPOTIFY_DATA_DIR, config.SPOTIFY_DATA_DIR, "directory"),
        MigrationItem("logs", config.LEGACY_LOG_ROOT, config.LOG_ROOT, "directory"),
        MigrationItem("temp", config.LEGACY_TEMP_ROOT, config.TEMP_ROOT, "directory"),
        MigrationItem("state", config.LEGACY_STATE_ROOT, config.STATE_ROOT, "directory"),
        MigrationItem("model_cache", config.LEGACY_MODEL_CACHE_ROOT, config.MODEL_CACHE_ROOT, "directory"),
        MigrationItem("profile_state", config.PROJECT_ROOT / ".lyra_profile", config.STATE_ROOT / "profile", "file"),
        MigrationItem("pause_state", config.PROJECT_ROOT / ".lyra_paused", config.STATE_ROOT / "pause.json", "file"),
    ]


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for candidate in path.rglob("*") if candidate.is_file())


def _copy_file(source: Path, target: Path, overwrite: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not overwrite and target.stat().st_size > 0:
            return "skipped_existing"
    shutil.copy2(source, target)
    return "copied"


def _copy_directory(source: Path, target: Path, overwrite: bool) -> str:
    target.mkdir(parents=True, exist_ok=True)
    source_files = _count_files(source)
    target_files = _count_files(target)
    if source_files == 0:
        return "skipped_empty"
    if target_files > 0 and not overwrite:
        return "skipped_existing"
    shutil.copytree(source, target, dirs_exist_ok=True)
    return "copied"


def _verify_item(item: MigrationItem) -> tuple[bool, str]:
    if not item.source.exists():
        return True, "source_missing"
    if not item.target.exists():
        return False, "target_missing"
    if item.kind == "file":
        try:
            source_size = item.source.stat().st_size
            target_size = item.target.stat().st_size
        except OSError as exc:
            return False, str(exc)
        if source_size > 0 and target_size < source_size:
            return False, f"target smaller than source ({target_size} < {source_size})"
        return True, "verified"
    source_count = _count_files(item.source)
    target_count = _count_files(item.target)
    if source_count > 0 and target_count < source_count:
        return False, f"target file count smaller than source ({target_count} < {source_count})"
    return True, "verified"


def build_data_root_report() -> dict[str, Any]:
    """Return the current data-root state and the supported next actions."""
    legacy_paths = config.detect_legacy_data_paths()
    migrate_command = "python -m oracle.cli data-root migrate --yes"
    defer_command = "$env:LYRA_USE_LEGACY_DATA_ROOT='1'"
    if config.legacy_data_override_allowed():
        state = "legacy_override"
    elif config.legacy_data_migration_required():
        state = "migration_required"
    elif legacy_paths:
        state = "legacy_data_present"
    else:
        state = "ready"
    return {
        "state": state,
        "data_root": str(config.DATA_ROOT),
        "build_root": str(config.BUILD_ROOT),
        "legacy_override": config.legacy_data_override_allowed(),
        "has_data_root_state": config.has_data_root_state(),
        "migration_required": config.legacy_data_migration_required(),
        "legacy_paths": {label: str(path) for label, path in legacy_paths.items()},
        "recommended_actions": {
            "migrate_now": migrate_command,
            "defer_temporarily": defer_command,
        },
        "available_actions": {
            "migrate": {
                "method": "POST",
                "path": "/api/runtime/data-root/migrate",
                "supports_overwrite": True,
            },
            "defer": {
                "method": "POST",
                "path": "/api/runtime/data-root/defer",
                "restart_required": True,
            },
        },
    }


def get_defer_payload() -> dict[str, Any]:
    """Return explicit defer instructions for temporary legacy fallback."""
    return {
        "legacy_override_required": True,
        "restart_required": True,
        "env_var": "LYRA_USE_LEGACY_DATA_ROOT",
        "value": "1",
        "powershell": "$env:LYRA_USE_LEGACY_DATA_ROOT='1'",
        "note": (
            "Temporary fallback only. Remove the override after migrating legacy data "
            "into LYRA_DATA_ROOT."
        ),
    }


def migrate_legacy_data(*, overwrite: bool = False) -> dict[str, Any]:
    """Copy detected legacy runtime data into the active `LYRA_DATA_ROOT`."""
    config.ensure_generated_dirs()
    report = build_data_root_report()
    actions: list[dict[str, Any]] = []
    failures = 0

    for item in _iter_migration_items():
        if not item.source.exists():
            continue

        action: dict[str, Any] = asdict(item)
        action["source"] = str(item.source)
        action["target"] = str(item.target)

        try:
            if item.kind == "file":
                action["result"] = _copy_file(item.source, item.target, overwrite=overwrite)
            else:
                action["result"] = _copy_directory(item.source, item.target, overwrite=overwrite)
            verified, verify_detail = _verify_item(item)
            action["verified"] = verified
            action["verify_detail"] = verify_detail
            if not verified:
                failures += 1
        except Exception as exc:  # noqa: BLE001
            failures += 1
            action["result"] = "error"
            action["verified"] = False
            action["verify_detail"] = str(exc)
            logger.warning("Legacy data migration failed for %s: %s", item.label, exc)

        actions.append(action)

    migrated_report = build_data_root_report()
    migrated_report["actions"] = actions
    migrated_report["failures"] = failures
    migrated_report["overwrite"] = overwrite
    migrated_report["migrated"] = failures == 0 and any(
        action.get("result") in {"copied", "skipped_existing", "skipped_empty"}
        for action in actions
    )
    return migrated_report
