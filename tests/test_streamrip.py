from __future__ import annotations

from pathlib import Path

from oracle.acquirers import streamrip


def test_is_available_false_when_binary_missing(monkeypatch) -> None:
    monkeypatch.setattr(streamrip, "_rip_binary", lambda: None)
    assert streamrip.is_available() is False


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
        out_dir = Path(command[command.index("--output") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.flac").write_bytes(b"fLaC")
        return _Completed()

    monkeypatch.setattr(streamrip.subprocess, "run", _fake_run)
    result = streamrip.download("Artist", "Title", output_dir=tmp_path)

    assert result["success"] is True
    assert result["path"].endswith("result.flac")
