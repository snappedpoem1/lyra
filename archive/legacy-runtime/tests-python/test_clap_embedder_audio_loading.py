from __future__ import annotations

from pathlib import Path

import numpy as np

from oracle.embedders.clap_embedder import CLAPEmbedder


def test_load_audio_uses_soundfile_fallback_when_librosa_load_fails(monkeypatch) -> None:
    class _FakeLibrosa:
        @staticmethod
        def load(*args, **kwargs):
            raise ZeroDivisionError("float division by zero")

        @staticmethod
        def resample(audio, orig_sr, target_sr):
            return audio

    class _FakeSoundFile:
        @staticmethod
        def read(*args, **kwargs):
            data = np.array([[0.1, -0.1], [0.4, -0.2], [0.0, 0.3]], dtype=np.float32)
            return data, 48000

    monkeypatch.setattr("oracle.embedders.clap_embedder.librosa", _FakeLibrosa())
    monkeypatch.setattr("oracle.embedders.clap_embedder.sf", _FakeSoundFile())

    embedder = CLAPEmbedder.__new__(CLAPEmbedder)
    audio = embedder._load_audio(Path("dummy.flac"), duration=30)

    assert audio is not None
    assert audio.dtype == np.float32
    assert np.isclose(float(np.max(np.abs(audio))), 1.0)


def test_load_audio_returns_none_for_silent_audio(monkeypatch) -> None:
    class _FakeLibrosa:
        @staticmethod
        def load(*args, **kwargs):
            return np.zeros(128, dtype=np.float32), 48000

    monkeypatch.setattr("oracle.embedders.clap_embedder.librosa", _FakeLibrosa())

    embedder = CLAPEmbedder.__new__(CLAPEmbedder)
    audio = embedder._load_audio(Path("silent.flac"), duration=30)

    assert audio is None
