"""Runtime service manifest for packaging and architecture policy."""

from __future__ import annotations

from typing import Any


def get_runtime_service_manifest() -> dict[str, dict[str, Any]]:
    """Return the authoritative runtime-service classification."""
    return {
        "backend_player": {
            "label": "Backend Player",
            "category": "core",
            "packaging_mode": "bundled",
            "required_for_core_app": True,
            "legacy_docker_supported": False,
            "notes": "Canonical playback authority in the packaged Lyra app.",
        },
        "qobuz": {
            "label": "Qobuz",
            "category": "acquisition",
            "packaging_mode": "internal_python",
            "required_for_core_app": False,
            "legacy_docker_supported": True,
            "notes": "Preferred hi-fi acquisition path; target is packaged direct integration.",
        },
        "streamrip": {
            "label": "Streamrip",
            "category": "acquisition",
            "packaging_mode": "bundled_tool",
            "required_for_core_app": False,
            "legacy_docker_supported": False,
            "notes": "Should be shipped as a managed runtime tool, not a container dependency.",
        },
        "spotdl": {
            "label": "SpotDL",
            "category": "acquisition",
            "packaging_mode": "bundled_tool",
            "required_for_core_app": False,
            "legacy_docker_supported": False,
            "notes": "Fallback acquisition tool intended for app-managed packaging.",
        },
        "slskd": {
            "label": "slskd",
            "category": "acquisition",
            "packaging_mode": "optional_external",
            "required_for_core_app": False,
            "legacy_docker_supported": True,
            "notes": "Optional external companion until Lyra internalizes equivalent queue/search behavior.",
        },
        "prowlarr": {
            "label": "Prowlarr",
            "category": "acquisition",
            "packaging_mode": "optional_external",
            "required_for_core_app": False,
            "legacy_docker_supported": True,
            "notes": "Indexer companion, no longer part of core-app runtime architecture.",
        },
        "realdebrid": {
            "label": "Real-Debrid",
            "category": "acquisition",
            "packaging_mode": "external_api",
            "required_for_core_app": False,
            "legacy_docker_supported": False,
            "notes": "External API provider; app integration is direct and Docker-independent.",
        },
        "lidarr": {
            "label": "Lidarr",
            "category": "ecosystem",
            "packaging_mode": "optional_external",
            "required_for_core_app": False,
            "legacy_docker_supported": True,
            "notes": "Optional ecosystem companion, not required for Lyra daily-driver use.",
        },
        "docker": {
            "label": "Docker",
            "category": "legacy_infra",
            "packaging_mode": "optional_legacy_layer",
            "required_for_core_app": False,
            "legacy_docker_supported": True,
            "notes": "Legacy compatibility layer only; not part of core architecture.",
        },
    }


def get_packaging_summary() -> dict[str, list[str]]:
    """Summarize packaging targets for the current architecture."""
    manifest = get_runtime_service_manifest()
    grouped: dict[str, list[str]] = {
        "bundle_now": [],
        "internalize_next": [],
        "optional_external": [],
        "external_api": [],
    }
    for service_id, payload in manifest.items():
        mode = str(payload.get("packaging_mode") or "")
        if mode == "bundled_tool" or mode == "bundled":
            grouped["bundle_now"].append(service_id)
        elif mode == "internal_python":
            grouped["internalize_next"].append(service_id)
        elif mode == "optional_external" or mode == "optional_legacy_layer":
            grouped["optional_external"].append(service_id)
        elif mode == "external_api":
            grouped["external_api"].append(service_id)
    return grouped
