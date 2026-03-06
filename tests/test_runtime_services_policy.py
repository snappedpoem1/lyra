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
