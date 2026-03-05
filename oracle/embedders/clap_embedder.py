"""CLAP embedding generator for audio and text.

Uses laion/larger_clap_music for music-specific embeddings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import os
import time
import logging
import threading
import warnings

# librosa is only needed for audio file loading. make it an optional dependency so
# the rest of the embedder still works in environments where librosa may be
# difficult to install (e.g. minimal containers).  If the import fails we
# keep the name around as None and log a warning; callers will surface a
# RuntimeError when they attempt to load audio.
try:
    import librosa
except ImportError:  # pragma: no cover - optional dependency
    librosa = None
    logging.warning("librosa not available; audio embedding will be disabled")

import numpy as np
import torch
from transformers import ClapModel, ClapProcessor
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Keep cold-start logs smaller and avoid terminal churn during first model load.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
try:
    from transformers.utils import logging as _hf_logging
    _hf_logging.set_verbosity_error()
    if hasattr(_hf_logging, "disable_progress_bar"):
        _hf_logging.disable_progress_bar()
except Exception:
    pass

# Music-specific CLAP model (better for music than general audio model)
DEFAULT_MODEL = "laion/larger_clap_music"
# Fallback to smaller model if larger one fails
FALLBACK_MODEL = "laion/clap-htsat-unfused"


class CLAPEmbedder:
    _shared_lock = threading.Lock()
    _shared_handles: dict[str, dict] = {}
    _skip_local_only_models: set[str] = set()

    def __init__(
        self,
        model_name: Optional[str] = None,
        cache_dir: Optional[str] = None,
        use_fallback: bool = True,
    ):
        # Try music-specific model first, fall back to general if needed
        self.model_name = model_name or os.getenv("LYRA_CLAP_MODEL", DEFAULT_MODEL)
        # Prefer CUDA first (NVIDIA), then DirectML fallback, then CPU.
        self._dml = False
        if torch.cuda.is_available():
            self.device = "cuda"
        else:
            try:
                import torch_directml  # type: ignore
                self.device = torch_directml.device()
                self._dml = True
            except ImportError:
                self.device = "cpu"
        
        # Use project cache dir to avoid Windows .cache file conflicts
        if cache_dir:
            self.cache_dir = cache_dir
        elif os.getenv("HF_HOME"):
            self.cache_dir = os.getenv("HF_HOME")
        else:
            # Default to project directory
            project_cache = Path(__file__).resolve().parents[2] / "hf_cache"
            project_cache.mkdir(parents=True, exist_ok=True)
            self.cache_dir = str(project_cache)
            # Also set env var so transformers uses it
            os.environ["HF_HOME"] = self.cache_dir
            os.environ["HUGGINGFACE_HUB_CACHE"] = str(project_cache / "hub")
        
        self.use_fallback = use_fallback
        self.processor = None
        self.model = None
        self._shared_enabled = os.getenv("LYRA_CLAP_SHARED_MODEL", "1").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self._shared_key = f"{self.model_name}|{self.cache_dir}|{self.device}"
        self._attach_or_load_model()

    @classmethod
    def _idle_unload_seconds(cls) -> float:
        raw = os.getenv("LYRA_CLAP_IDLE_UNLOAD_SECONDS", "0").strip()
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 0.0

    @classmethod
    def _evict_entry(cls, key: str) -> None:
        entry = cls._shared_handles.pop(key, None)
        if not entry:
            return
        # Drop strong refs and release accelerator caches.
        entry["model"] = None
        entry["processor"] = None
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @classmethod
    def evict_idle(cls, *, force: bool = False) -> int:
        """Evict shared CLAP handles that are idle or all handles when force=True."""
        with cls._shared_lock:
            if force:
                keys = list(cls._shared_handles.keys())
            else:
                ttl = cls._idle_unload_seconds()
                if ttl <= 0:
                    return 0
                now = time.time()
                keys = [
                    key
                    for key, entry in cls._shared_handles.items()
                    if entry.get("refs", 0) <= 0 and (now - float(entry.get("last_used", now))) >= ttl
                ]
            for key in keys:
                cls._evict_entry(key)
            return len(keys)

    @classmethod
    def shared_stats(cls) -> dict:
        with cls._shared_lock:
            return {
                "enabled": os.getenv("LYRA_CLAP_SHARED_MODEL", "1").strip().lower() in {"1", "true", "yes", "on"},
                "handles": len(cls._shared_handles),
                "keys": list(cls._shared_handles.keys()),
                "idle_unload_seconds": cls._idle_unload_seconds(),
            }

    def _attach_or_load_model(self) -> None:
        if not self._shared_enabled:
            self._load_model_with_retry()
            return

        # Opportunistic cleanup before potential new allocations.
        self.__class__.evict_idle(force=False)

        with self.__class__._shared_lock:
            existing = self.__class__._shared_handles.get(self._shared_key)
            if existing is not None:
                self.model_name = existing["model_name"]
                existing["refs"] = int(existing.get("refs", 0)) + 1
                existing["last_used"] = time.time()
                logger.info("Reusing shared CLAP model: %s on %s", self.model_name, self.device)
                # Shared mode reads runtime objects from the shared handle.
                self.processor = None
                self.model = None
                return

            # Hold lock while loading to avoid parallel duplicate loads.
            self._load_model_with_retry()
            self.__class__._shared_handles[self._shared_key] = {
                "processor": self.processor,
                "model": self.model,
                "model_name": self.model_name,
                "refs": 1,
                "last_used": time.time(),
            }
            # Shared mode reads runtime objects from the shared handle.
            self.processor = None
            self.model = None

    def _runtime(self):
        """Return (processor, model), rehydrating shared handle if needed."""
        if not self._shared_enabled:
            return self.processor, self.model

        with self.__class__._shared_lock:
            entry = self.__class__._shared_handles.get(self._shared_key)
            if (
                entry is None
                or entry.get("processor") is None
                or entry.get("model") is None
            ):
                self._load_model_with_retry()
                self.__class__._shared_handles[self._shared_key] = {
                    "processor": self.processor,
                    "model": self.model,
                    "model_name": self.model_name,
                    "refs": max(1, int(entry.get("refs", 0))) if entry else 1,
                    "last_used": time.time(),
                }
                entry = self.__class__._shared_handles[self._shared_key]
                # Drop per-instance refs in shared mode.
                self.processor = None
                self.model = None

            entry["last_used"] = time.time()
            return entry["processor"], entry["model"]

    def close(self) -> None:
        """Release this instance's shared-handle reference."""
        if not self._shared_enabled:
            return
        with self.__class__._shared_lock:
            entry = self.__class__._shared_handles.get(self._shared_key)
            if not entry:
                return
            entry["refs"] = max(0, int(entry.get("refs", 0)) - 1)
            entry["last_used"] = time.time()
        self.__class__.evict_idle(force=False)

    # laion/larger_clap_music stores weights in a PR branch, not main.
    # Specifying this revision lets us skip all HF API network calls (~30-60s)
    # when the cache is warm.  Override via LYRA_CLAP_REVISION env var if needed.
    _REVISION_HINTS: dict[str, str] = {}

    def _load_model_with_retry(self, retries: int = 3, backoff: float = 2.0) -> None:
        models_to_try = [self.model_name]
        if self.use_fallback and self.model_name != FALLBACK_MODEL:
            models_to_try.append(FALLBACK_MODEL)

        last_error: Optional[Exception] = None

        for model_name in models_to_try:
            # Try local-first (skip network) using known revision hint, then fall
            # back to network-enabled load so a cold cache still works.
            revision_hint = os.getenv(
                "LYRA_CLAP_REVISION",
                self._REVISION_HINTS.get(model_name),
            )
            skip_local_probe = os.getenv("LYRA_CLAP_SKIP_LOCAL_PROBE", "0").strip().lower() in {
                "1", "true", "yes", "on"
            }
            load_variants: list[dict] = []
            if (
                not skip_local_probe
                and revision_hint
                and model_name not in self.__class__._skip_local_only_models
            ):
                load_variants.append(
                    {"revision": revision_hint, "local_files_only": True, "use_safetensors": True}
                )
            # Always include a network-enabled fallback (no revision pin)
            load_variants.append({"use_safetensors": True})

            for attempt in range(1, retries + 1):
                for kwargs in load_variants:
                    try:
                        local_only = kwargs.get("local_files_only", False)
                        mode = "local" if local_only else "network"
                        logger.info(
                            f"Loading CLAP model: {model_name} [{mode}] (attempt {attempt})"
                        )
                        self.processor = ClapProcessor.from_pretrained(
                            model_name,
                            cache_dir=self.cache_dir,
                            revision=kwargs.get("revision"),
                            local_files_only=local_only,
                        )
                        self.model = ClapModel.from_pretrained(
                            model_name,
                            cache_dir=self.cache_dir,
                            revision=kwargs.get("revision"),
                            local_files_only=local_only,
                            use_safetensors=kwargs.get("use_safetensors", False),
                            low_cpu_mem_usage=True,
                        ).to(self.device)
                        self.model.eval()
                        self.model_name = model_name
                        logger.info(f"CLAP model loaded: {model_name} on {self.device} [{mode}]")
                        return
                    except Exception as exc:
                        last_error = exc
                        if local_only:
                            # Avoid repeating the same guaranteed local-only miss for this model.
                            self.__class__._skip_local_only_models.add(model_name)
                        logger.warning(f"Load variant {kwargs} failed: {exc}")
                        # Only sleep between full retry cycles, not between variants
                if attempt < retries:
                    time.sleep(backoff ** attempt)

            logger.warning(f"All attempts failed for {model_name}, trying fallback...")

        raise RuntimeError(f"Failed to load CLAP model: {last_error}")

    def _load_audio(self, file_path: Path, duration: int = 30) -> Optional[np.ndarray]:
        # librosa is required for audio loading. raise early if it's missing so
        # callers can take appropriate action (logging/error return) instead of
        # getting a confusing AttributeError deep in the call stack.
        if librosa is None:
            raise RuntimeError("librosa is not installed; audio loading unavailable")

        try:
            # Suppress librosa warnings about fallback
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                audio, _sr = librosa.load(str(file_path), sr=48000, mono=True, duration=duration)
            
            if audio is None or (hasattr(audio, 'size') and audio.size == 0):
                logger.warning(f"Empty audio loaded from {file_path}")
                return None
            
            audio = librosa.util.normalize(audio)
            return audio
        except Exception as e:
            logger.warning(f"Failed to load audio {file_path}: {type(e).__name__}: {e}")
            return None

    def embed_audio(self, file_path: Path, duration: int = 30) -> Optional[np.ndarray]:
        processor, model = self._runtime()
        try:
            audio = self._load_audio(file_path, duration=duration)
        except RuntimeError as exc:
            logger.error(str(exc))
            return None

        if audio is None:
            return None

        try:
            inputs = processor(audio=audio, sampling_rate=48000, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with torch.no_grad():
                outputs = model.get_audio_features(**inputs)
                # Handle both tensor and BaseModelOutputWithPooling returns
                if hasattr(outputs, 'cpu'):
                    # It's a tensor
                    audio_features = outputs.cpu().numpy()[0]
                elif hasattr(outputs, 'last_hidden_state'):
                    # It's a model output object - use pooler_output or mean of last_hidden_state
                    if hasattr(outputs, 'pooler_output') and outputs.pooler_output is not None:
                        audio_features = outputs.pooler_output.cpu().numpy()[0]
                    else:
                        audio_features = outputs.last_hidden_state.mean(dim=1).cpu().numpy()[0]
                else:
                    # Try to get the embedding directly
                    audio_features = outputs[0].cpu().numpy() if isinstance(outputs, tuple) else outputs.cpu().numpy()[0]
            return audio_features
        except RuntimeError as exc:
            is_gpu = self._dml or str(self.device) not in ("cpu",)
            if "out of memory" in str(exc).lower() and is_gpu:
                logger.warning("GPU OOM, falling back to CPU")
                self._dml = False
                self.device = "cpu"
                if self._shared_enabled:
                    with self.__class__._shared_lock:
                        entry = self.__class__._shared_handles.get(self._shared_key)
                        if entry and entry.get("model") is not None:
                            entry["model"] = entry["model"].to(self.device)
                            entry["last_used"] = time.time()
                else:
                    self.model = self.model.to(self.device)
                return self.embed_audio(file_path, duration=duration)
            logger.error(f"Embedding failed for {file_path}: {exc}")
            return None
        except Exception as exc:
            logger.error(f"Embedding failed for {file_path}: {type(exc).__name__}: {exc}")
            return None

    def embed_audio_batch(
        self,
        file_paths: list,
        duration: int = 30,
        batch_size: int = 8,
    ) -> dict:
        """Embed multiple audio files in batches â€” single GPU forward pass per batch.

        Args:
            file_paths: List of Path objects.
            duration: Seconds of audio to load per file.
            batch_size: Files per GPU forward pass. 8 is safe for DirectML/6GB VRAM.

        Returns:
            Dict mapping each Path to its embedding np.ndarray (or None on failure).
        """
        processor, model = self._runtime()
        from concurrent.futures import ThreadPoolExecutor

        results: dict = {}

        # Load audio in parallel (I/O bound)
        def _load(p) -> tuple:
            try:
                return p, self._load_audio(p, duration=duration)
            except RuntimeError as exc:
                logger.error(str(exc))
                return p, None

        with ThreadPoolExecutor(max_workers=min(8, len(file_paths))) as exe:
            loaded = list(exe.map(_load, file_paths))

        valid = [(p, a) for p, a in loaded if a is not None]
        for p, a in loaded:
            if a is None:
                results[p] = None

        # GPU forward pass in batches
        for start in range(0, len(valid), batch_size):
            chunk = valid[start:start + batch_size]
            paths_chunk = [p for p, _ in chunk]
            audios_chunk = [a for _, a in chunk]

            try:
                inputs = processor(
                    audio=audios_chunk,
                    sampling_rate=48000,
                    return_tensors="pt",
                    padding=True,
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                with torch.no_grad():
                    features = model.get_audio_features(**inputs)
                    if hasattr(features, "cpu"):
                        embeddings = features.cpu().numpy()
                    elif hasattr(features, "pooler_output") and features.pooler_output is not None:
                        embeddings = features.pooler_output.cpu().numpy()
                    else:
                        embeddings = features.last_hidden_state.mean(dim=1).cpu().numpy()

                for path, emb in zip(paths_chunk, embeddings):
                    results[path] = emb

            except RuntimeError as exc:
                is_gpu = self._dml or str(self.device) not in ("cpu",)
                if "out of memory" in str(exc).lower() and is_gpu:
                    logger.warning(f"[CLAP] OOM at batch_size={batch_size}, falling back to 1-by-1")
                    for p, a in chunk:
                        results[p] = self.embed_audio(p, duration=duration)
                else:
                    logger.error(f"[CLAP] Batch error: {exc}")
                    for p, _ in chunk:
                        results[p] = None
            except Exception as exc:
                logger.error(f"[CLAP] Batch error: {type(exc).__name__}: {exc}")
                for p, _ in chunk:
                    results[p] = None

        return results

    def embed_text(self, text: str) -> Optional[np.ndarray]:
        processor, model = self._runtime()
        try:
            inputs = processor(text=[text], return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with torch.no_grad():
                outputs = model.get_text_features(**inputs)
                # Handle both tensor and model output objects
                if hasattr(outputs, 'cpu'):
                    text_features = outputs.cpu().numpy()[0]
                elif hasattr(outputs, 'pooler_output') and outputs.pooler_output is not None:
                    text_features = outputs.pooler_output.cpu().numpy()[0]
                elif hasattr(outputs, 'last_hidden_state'):
                    text_features = outputs.last_hidden_state.mean(dim=1).cpu().numpy()[0]
                else:
                    text_features = outputs[0].cpu().numpy() if isinstance(outputs, tuple) else None
            return text_features
        except Exception as e:
            logger.error(f"Text embedding failed: {e}")
            return None

    def get_model_info(self) -> dict:
        """Return info about the loaded model."""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "embedding_dim": 512,  # CLAP models output 512-dim vectors
        }


def _main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(level=logging.INFO)
    
    print("Loading CLAP model (music-specific)...")
    embedder = CLAPEmbedder()
    
    print(f"Model info: {embedder.get_model_info()}")
    
    vector = embedder.embed_text("dreamy atmospheric synth pads")
    if vector is None:
        print("Text embed failed")
    else:
        print(f"Text embedding dim: {len(vector)}")
    
    # Test with an actual audio file if available
    import sys
    if len(sys.argv) > 1:
        test_file = Path(sys.argv[1])
        if test_file.exists():
            print(f"\nTesting audio file: {test_file}")
            vec = embedder.embed_audio(test_file)
            if vec is None:
                print("Audio embed FAILED")
            else:
                print(f"Audio embedding dim: {len(vec)}")
                print(f"First 5 values: {vec[:5]}")
        else:
            print(f"File not found: {test_file}")


if __name__ == "__main__":
    _main()
