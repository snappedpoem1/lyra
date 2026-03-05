from __future__ import annotations

from oracle.embedders.clap_embedder import CLAPEmbedder


def _reset_runtime() -> None:
    CLAPEmbedder.evict_idle(force=True)
    CLAPEmbedder._shared_handles.clear()


def test_shared_runtime_deduplicates_model_load(monkeypatch, tmp_path):
    _reset_runtime()
    monkeypatch.setenv("LYRA_CLAP_SHARED_MODEL", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    load_calls = {"n": 0}

    def _fake_load(self, retries=3, backoff=2.0):
        load_calls["n"] += 1
        self.processor = object()
        self.model = object()

    monkeypatch.setattr(CLAPEmbedder, "_load_model_with_retry", _fake_load)

    a = CLAPEmbedder(model_name="fake-clap", use_fallback=False)
    b = CLAPEmbedder(model_name="fake-clap", use_fallback=False)

    assert load_calls["n"] == 1
    assert CLAPEmbedder.shared_stats()["handles"] == 1
    # Ensure cleanup path remains valid for both instances.
    a.close()
    b.close()


def test_force_unload_rehydrates_on_next_runtime_access(monkeypatch, tmp_path):
    _reset_runtime()
    monkeypatch.setenv("LYRA_CLAP_SHARED_MODEL", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    load_calls = {"n": 0}

    def _fake_load(self, retries=3, backoff=2.0):
        load_calls["n"] += 1
        self.processor = object()
        self.model = object()

    monkeypatch.setattr(CLAPEmbedder, "_load_model_with_retry", _fake_load)

    embedder = CLAPEmbedder(model_name="fake-clap", use_fallback=False)
    assert load_calls["n"] == 1

    evicted = CLAPEmbedder.evict_idle(force=True)
    assert evicted == 1
    assert CLAPEmbedder.shared_stats()["handles"] == 0

    processor, model = embedder._runtime()
    assert processor is not None
    assert model is not None
    assert load_calls["n"] == 2


def test_local_only_probe_is_skipped_after_first_miss(monkeypatch, tmp_path):
    _reset_runtime()
    CLAPEmbedder._skip_local_only_models.clear()
    monkeypatch.setenv("LYRA_CLAP_SHARED_MODEL", "0")
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    # Supply a revision hint via env var so the local-only probe is attempted
    monkeypatch.setenv("LYRA_CLAP_REVISION", "test-revision")

    calls = {"local_only": 0, "network": 0}

    class _FakeModel:
        def to(self, _device):
            return self

        def eval(self):
            return self

    def _fake_processor_from_pretrained(model_name, **kwargs):
        local_only = bool(kwargs.get("local_files_only", False))
        if local_only:
            calls["local_only"] += 1
            raise RuntimeError("cache miss")
        calls["network"] += 1
        return object()

    def _fake_model_from_pretrained(model_name, **kwargs):
        local_only = bool(kwargs.get("local_files_only", False))
        if local_only:
            raise RuntimeError("cache miss")
        return _FakeModel()

    monkeypatch.setattr("oracle.embedders.clap_embedder.ClapProcessor.from_pretrained", _fake_processor_from_pretrained)
    monkeypatch.setattr("oracle.embedders.clap_embedder.ClapModel.from_pretrained", _fake_model_from_pretrained)

    CLAPEmbedder(model_name="laion/larger_clap_music", cache_dir=str(tmp_path), use_fallback=False)
    CLAPEmbedder(model_name="laion/larger_clap_music", cache_dir=str(tmp_path), use_fallback=False)

    # First instance probes local-only once; second skips directly to network.
    assert calls["local_only"] == 1
    assert calls["network"] == 2


def test_local_only_probe_can_be_disabled_via_env(monkeypatch, tmp_path):
    _reset_runtime()
    CLAPEmbedder._skip_local_only_models.clear()
    monkeypatch.setenv("LYRA_CLAP_SHARED_MODEL", "0")
    monkeypatch.setenv("LYRA_CLAP_SKIP_LOCAL_PROBE", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    calls = {"local_only": 0, "network": 0}

    class _FakeModel:
        def to(self, _device):
            return self

        def eval(self):
            return self

    def _fake_processor_from_pretrained(model_name, **kwargs):
        if bool(kwargs.get("local_files_only", False)):
            calls["local_only"] += 1
            raise RuntimeError("unexpected local probe")
        calls["network"] += 1
        return object()

    def _fake_model_from_pretrained(model_name, **kwargs):
        return _FakeModel()

    monkeypatch.setattr("oracle.embedders.clap_embedder.ClapProcessor.from_pretrained", _fake_processor_from_pretrained)
    monkeypatch.setattr("oracle.embedders.clap_embedder.ClapModel.from_pretrained", _fake_model_from_pretrained)

    CLAPEmbedder(model_name="laion/larger_clap_music", cache_dir=str(tmp_path), use_fallback=False)

    assert calls["local_only"] == 0
    assert calls["network"] == 1
