from __future__ import annotations

import lyra_api
import oracle.api.blueprints.core as core_bp
import pytest


@pytest.fixture
def client():
    lyra_api.app.config.update(TESTING=True)
    with lyra_api.app.test_client() as test_client:
        yield test_client


def test_runtime_data_root_status_contract(client, monkeypatch) -> None:
    monkeypatch.setattr(
        core_bp,
        "build_data_root_report",
        lambda: {
            "state": "migration_required",
            "data_root": "C:/Users/Test/AppData/Local/Lyra/dev",
            "build_root": "C:/MusicOracle/.lyra-build",
            "legacy_override": False,
            "has_data_root_state": False,
            "migration_required": True,
            "legacy_paths": {"database": "C:/MusicOracle/lyra_registry.db"},
            "recommended_actions": {
                "migrate_now": "python -m oracle.cli data-root migrate --yes",
                "defer_temporarily": "$env:LYRA_USE_LEGACY_DATA_ROOT='1'",
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
        },
    )

    response = client.get("/api/runtime/data-root")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "migration_required"
    assert payload["available_actions"]["migrate"]["path"] == "/api/runtime/data-root/migrate"
    assert payload["available_actions"]["defer"]["path"] == "/api/runtime/data-root/defer"


def test_runtime_data_root_migrate_endpoint_accepts_overwrite(client, monkeypatch) -> None:
    call: dict[str, bool] = {}

    def _fake_migrate_legacy_data(*, overwrite: bool = False) -> dict[str, object]:
        call["overwrite"] = overwrite
        return {
            "state": "ready",
            "migration_required": False,
            "migrated": True,
            "failures": 0,
        }

    monkeypatch.setattr(core_bp, "migrate_legacy_data", _fake_migrate_legacy_data)

    response = client.post("/api/runtime/data-root/migrate", json={"overwrite": True})

    assert response.status_code == 200
    assert call["overwrite"] is True
    payload = response.get_json()
    assert payload["migrated"] is True
    assert payload["migration_required"] is False


def test_runtime_data_root_migrate_endpoint_rejects_invalid_overwrite(client) -> None:
    response = client.post("/api/runtime/data-root/migrate", json={"overwrite": "later"})

    assert response.status_code == 400
    payload = response.get_json()
    assert "boolean" in payload["error"]


def test_runtime_data_root_defer_endpoint_returns_guidance(client, monkeypatch) -> None:
    monkeypatch.setattr(
        core_bp,
        "build_data_root_report",
        lambda: {"state": "migration_required", "migration_required": True},
    )
    monkeypatch.setattr(
        core_bp,
        "get_defer_payload",
        lambda: {
            "legacy_override_required": True,
            "restart_required": True,
            "env_var": "LYRA_USE_LEGACY_DATA_ROOT",
            "value": "1",
            "powershell": "$env:LYRA_USE_LEGACY_DATA_ROOT='1'",
            "note": "Temporary fallback only.",
        },
    )

    response = client.post("/api/runtime/data-root/defer")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["env_var"] == "LYRA_USE_LEGACY_DATA_ROOT"
    assert payload["restart_required"] is True
    assert payload["data_root"]["migration_required"] is True
