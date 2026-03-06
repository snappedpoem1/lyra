from __future__ import annotations

import os
from pathlib import Path

from oracle.acquirers import streamrip


def test_is_available_false_when_binary_missing(monkeypatch) -> None:
    monkeypatch.setattr(streamrip, "_rip_binary", lambda: None)
    assert streamrip.is_available() is False


def test_build_command_uses_streamrip_2x_syntax(tmp_path: Path) -> None:
    """Default command must use streamrip 2.x: rip -f <dir> search <source> track <query> --first."""
    cmd = streamrip._build_command("rip", "Burial Archangel", tmp_path)
    assert cmd[0] == "rip"
    assert "-f" in cmd
    assert str(tmp_path) == cmd[cmd.index("-f") + 1]
    assert "search" in cmd
    assert "track" in cmd
    assert "--first" in cmd
    assert "Burial Archangel" in cmd


def test_build_command_respects_source_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LYRA_STREAMRIP_SOURCE", "tidal")
    cmd = streamrip._build_command("rip", "Test Query", tmp_path)
    assert "tidal" in cmd


def test_build_command_respects_template_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LYRA_STREAMRIP_CMD_TEMPLATE", "{binary} custom oneword {output_dir}")
    cmd = streamrip._build_command("rip", "oneword", tmp_path)
    assert cmd == ["rip", "custom", "oneword", str(tmp_path)]


def test_download_fails_cleanly_without_binary(monkeypatch) -> None:
    monkeypatch.setattr(streamrip, "_rip_binary", lambda: None)
    result = streamrip.download("Artist", "Title")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_download_success_when_audio_file_created(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(streamrip, "_rip_binary", lambda: "rip")

    class _Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_run(command, capture_output, text, timeout, check):  # noqa: ANN001
        # New streamrip 2.x CLI: rip -f <output_dir> search <source> track <query> --first
        out_dir = Path(command[command.index("-f") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.flac").write_bytes(b"fLaC")
        return _Completed()

    monkeypatch.setattr(streamrip.subprocess, "run", _fake_run)
    result = streamrip.download("Artist", "Title", output_dir=tmp_path)

    assert result["success"] is True
    assert result["path"].endswith("result.flac")
