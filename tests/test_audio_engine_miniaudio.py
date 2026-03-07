from __future__ import annotations

import sys
from pathlib import Path

from oracle.player.audio_engine import MiniaudioPlaybackEngine


class _FakePlaybackDevice:
    def __init__(self, **_: object) -> None:
        self.started = 0
        self.stopped = 0
        self.closed = 0

    def start(self, callback_generator):
        self.started += 1
        callback_generator.send(1)

    def stop(self) -> None:
        self.stopped += 1

    def close(self) -> None:
        self.closed += 1


class _FakeInfo:
    sample_rate = 44100
    nchannels = 2
    duration = 3.0


class _FakeMiniaudioModule:
    class SampleFormat:
        SIGNED16 = object()

    PlaybackDevice = _FakePlaybackDevice

    @staticmethod
    def get_file_info(_: str) -> _FakeInfo:
        return _FakeInfo()

    @staticmethod
    def stream_file(
        _: str,
        output_format=None,
        nchannels: int = 2,
        sample_rate: int = 44100,
        frames_to_read: int = 2048,
        seek_frame: int = 0,
    ):
        _ = (output_format, nchannels, sample_rate, seek_frame)

        def _generator():
            requested_frames = yield b""
            while True:
                requested_frames = yield b"\x00\x00" * max(1, requested_frames)

        generator = _generator()
        next(generator)
        return generator

    @staticmethod
    def stream_with_callbacks(
        sample_stream,
        progress_callback=None,
        frame_process_method=None,
        end_callback=None,
    ):
        _ = end_callback

        def _generator():
            frame_count = yield b""
            while True:
                frame = sample_stream.send(frame_count)
                if frame_process_method:
                    frame = frame_process_method(frame)
                if progress_callback:
                    progress_callback(frame_count)
                frame_count = yield frame

        return _generator()


def test_miniaudio_engine_primes_callback_generator(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "miniaudio", _FakeMiniaudioModule())
    audio_path = tmp_path / "tone.flac"
    audio_path.write_bytes(b"fake-audio")

    engine = MiniaudioPlaybackEngine()

    duration_ms = engine.play(audio_path)

    assert duration_ms == 3000
    assert engine.position_ms() == 1 * 1000 // 44100