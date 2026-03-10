"""Backend audio playback engine abstraction with miniaudio implementation."""

from __future__ import annotations

from array import array
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class PlaybackEngine(Protocol):
    """Playback engine interface used by the player service."""

    @property
    def is_available(self) -> bool:
        """Whether the engine can produce audio output."""

    def play(
        self,
        filepath: Path,
        *,
        start_position_ms: int = 0,
        volume: float = 0.82,
        muted: bool = False,
    ) -> int | None:
        """Start playback and return duration in milliseconds when available."""

    def resume(self) -> None:
        """Resume playback from current position."""

    def pause(self) -> None:
        """Pause playback preserving position."""

    def seek(self, position_ms: int) -> None:
        """Seek to target position in milliseconds."""

    def stop(self) -> None:
        """Stop playback and release active device resources."""

    def set_volume(self, volume: float) -> None:
        """Set linear volume gain in range [0, 1]."""

    def set_muted(self, muted: bool) -> None:
        """Mute/unmute audio output."""

    def position_ms(self) -> int | None:
        """Return current playback position in milliseconds, if known."""

    def is_finished(self) -> bool:
        """Return True if current stream reached end-of-file."""

    def close(self) -> None:
        """Close and cleanup all resources."""


class NullPlaybackEngine:
    """No-op playback engine used when miniaudio is unavailable."""

    @property
    def is_available(self) -> bool:
        return False

    def play(
        self,
        filepath: Path,
        *,
        start_position_ms: int = 0,
        volume: float = 0.82,
        muted: bool = False,
    ) -> int | None:
        _ = (filepath, start_position_ms, volume, muted)
        return None

    def resume(self) -> None:
        return None

    def pause(self) -> None:
        return None

    def seek(self, position_ms: int) -> None:
        _ = position_ms

    def stop(self) -> None:
        return None

    def set_volume(self, volume: float) -> None:
        _ = volume

    def set_muted(self, muted: bool) -> None:
        _ = muted

    def position_ms(self) -> int | None:
        return None

    def is_finished(self) -> bool:
        return False

    def close(self) -> None:
        return None


class MiniaudioPlaybackEngine:
    """miniaudio-based playback engine with seek/resume support."""

    def __init__(self) -> None:
        try:
            import miniaudio as _miniaudio

            self._miniaudio = _miniaudio
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("miniaudio unavailable, falling back to simulated playback: %s", exc)
            self._miniaudio = None
            self._available = False

        self._lock = RLock()
        self._device: Any = None
        self._file_path: Path | None = None
        self._sample_rate: int = 44100
        self._nchannels: int = 2
        self._duration_ms: int = 0
        self._position_frame: int = 0
        self._start_frame: int = 0
        self._paused = False
        self._finished = False
        self._volume = 0.82
        self._muted = False

    @property
    def is_available(self) -> bool:
        return self._available

    def _gain(self) -> float:
        if self._muted:
            return 0.0
        return max(0.0, min(1.0, self._volume))

    def _frame_processor(self, frames: bytes | array[Any]) -> bytes | array[Any]:
        gain = self._gain()
        if gain >= 0.999:
            return frames
        if isinstance(frames, array):
            if frames.typecode != "h":
                return frames
            scaled = array("h", frames)
            for index, sample in enumerate(scaled):
                value = int(sample * gain)
                if value > 32767:
                    value = 32767
                elif value < -32768:
                    value = -32768
                scaled[index] = value
            return scaled
        raw = array("h")
        raw.frombytes(frames)
        for index, sample in enumerate(raw):
            value = int(sample * gain)
            if value > 32767:
                value = 32767
            elif value < -32768:
                value = -32768
            raw[index] = value
        return raw.tobytes()

    def _on_progress(self, frames_played: int) -> None:
        with self._lock:
            self._position_frame = max(0, self._start_frame + int(frames_played))

    def _on_end(self) -> None:
        with self._lock:
            self._finished = True

    def _prime_callback_stream(self, stream: Any) -> Any:
        try:
            next(stream)
        except StopIteration:
            return stream
        return stream

    def _build_stream(self, seek_frame: int) -> Any:
        base_stream = self._miniaudio.stream_file(
            str(self._file_path),
            output_format=self._miniaudio.SampleFormat.SIGNED16,
            nchannels=self._nchannels,
            sample_rate=self._sample_rate,
            frames_to_read=2048,
            seek_frame=max(0, seek_frame),
        )
        stream = self._miniaudio.stream_with_callbacks(
            base_stream,
            progress_callback=self._on_progress,
            frame_process_method=self._frame_processor,
            end_callback=self._on_end,
        )
        return self._prime_callback_stream(stream)

    def _rebuild_device(self) -> None:
        if self._device:
            try:
                self._device.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._device.close()
            except Exception:  # noqa: BLE001
                pass
            self._device = None
        self._device = self._miniaudio.PlaybackDevice(
            output_format=self._miniaudio.SampleFormat.SIGNED16,
            nchannels=self._nchannels,
            sample_rate=self._sample_rate,
            buffersize_msec=120,
            app_name="Lyra Oracle",
        )

    def play(
        self,
        filepath: Path,
        *,
        start_position_ms: int = 0,
        volume: float = 0.82,
        muted: bool = False,
    ) -> int | None:
        if not self._available:
            return None
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"audio file does not exist: {path}")

        info = self._miniaudio.get_file_info(str(path))
        with self._lock:
            self._file_path = path
            self._sample_rate = max(1, int(info.sample_rate))
            self._nchannels = max(1, int(info.nchannels))
            self._duration_ms = max(0, int(float(info.duration) * 1000))
            self._volume = float(volume)
            self._muted = bool(muted)
            self._finished = False
            self._paused = False
            self._start_frame = max(0, int((start_position_ms / 1000.0) * self._sample_rate))
            self._position_frame = self._start_frame
            self._rebuild_device()
            stream = self._build_stream(self._start_frame)
            self._device.start(stream)
            return self._duration_ms

    def resume(self) -> None:
        if not self._available:
            return
        with self._lock:
            if not self._file_path:
                return
            if not self._paused:
                return
            if not self._device:
                self._rebuild_device()
            self._start_frame = self._position_frame
            self._finished = False
            stream = self._build_stream(self._start_frame)
            self._device.start(stream)
            self._paused = False

    def pause(self) -> None:
        if not self._available:
            return
        with self._lock:
            if not self._device:
                return
            self._device.stop()
            self._paused = True

    def seek(self, position_ms: int) -> None:
        if not self._available:
            return
        with self._lock:
            if not self._file_path:
                return
            target_ms = max(0, position_ms)
            if self._duration_ms > 0:
                target_ms = min(target_ms, self._duration_ms)
            target_frame = int((target_ms / 1000.0) * self._sample_rate)
            self._start_frame = target_frame
            self._position_frame = target_frame
            self._finished = False
            if self._paused:
                return
            if not self._device:
                self._rebuild_device()
            self._device.stop()
            stream = self._build_stream(target_frame)
            self._device.start(stream)

    def stop(self) -> None:
        if not self._available:
            return
        with self._lock:
            if self._device:
                try:
                    self._device.stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._device.close()
                except Exception:  # noqa: BLE001
                    pass
                self._device = None
            self._paused = False
            self._finished = False

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, float(volume)))

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self._muted = bool(muted)

    def position_ms(self) -> int | None:
        if not self._available:
            return None
        with self._lock:
            return int((self._position_frame / self._sample_rate) * 1000)

    def is_finished(self) -> bool:
        if not self._available:
            return False
        with self._lock:
            return self._finished

    def close(self) -> None:
        self.stop()


def create_playback_engine() -> PlaybackEngine:
    """Create best-available playback engine implementation."""
    engine = MiniaudioPlaybackEngine()
    if engine.is_available:
        return engine
    return NullPlaybackEngine()
