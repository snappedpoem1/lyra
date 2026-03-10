from __future__ import annotations

import json
from pathlib import Path

import oracle.runtime_state as runtime_state


def _configure_runtime_state_paths(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    state_root = tmp_path / "state"
    profile_file = state_root / "profile"
    pause_file = state_root / "pause.json"
    legacy_profile = tmp_path / ".lyra_profile"
    legacy_pause = tmp_path / ".lyra_paused"

    monkeypatch.setattr(runtime_state, "_PROFILE_FILE", profile_file)
    monkeypatch.setattr(runtime_state, "_PROFILE_FILE_LEGACY", legacy_profile)
    monkeypatch.setattr(runtime_state, "_PAUSE_FILE", pause_file)
    monkeypatch.setattr(runtime_state, "_PAUSE_FILE_LEGACY", legacy_pause)
    monkeypatch.setattr(runtime_state, "ensure_generated_dirs", lambda: state_root.mkdir(parents=True, exist_ok=True))

    return {
        "profile": profile_file,
        "pause": pause_file,
        "legacy_profile": legacy_profile,
        "legacy_pause": legacy_pause,
    }


def test_get_profile_falls_back_to_legacy_file(monkeypatch, tmp_path: Path) -> None:
    paths = _configure_runtime_state_paths(monkeypatch, tmp_path)
    paths["legacy_profile"].write_text("performance", encoding="utf-8")

    assert runtime_state.get_profile() == "performance"


def test_set_profile_writes_to_state_root(monkeypatch, tmp_path: Path) -> None:
    paths = _configure_runtime_state_paths(monkeypatch, tmp_path)

    value = runtime_state.set_profile("quiet")

    assert value == "quiet"
    assert paths["profile"].read_text(encoding="utf-8") == "quiet"
    assert not paths["legacy_profile"].exists()


def test_resume_clears_new_and_legacy_pause_files(monkeypatch, tmp_path: Path) -> None:
    paths = _configure_runtime_state_paths(monkeypatch, tmp_path)
    paths["pause"].parent.mkdir(parents=True, exist_ok=True)
    paths["pause"].write_text(json.dumps({"paused": True, "reason": "new"}), encoding="utf-8")
    paths["legacy_pause"].write_text(json.dumps({"paused": True, "reason": "legacy"}), encoding="utf-8")

    paused, reason = runtime_state.is_paused()
    assert paused is True
    assert reason == "new"

    runtime_state.resume()

    assert not paths["pause"].exists()
    assert not paths["legacy_pause"].exists()
