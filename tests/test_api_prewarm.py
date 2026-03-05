from __future__ import annotations

import oracle.api.app as app_mod


def test_prewarm_disabled_noop(monkeypatch):
    called = {"n": 0}
    monkeypatch.setenv("LYRA_CLAP_PREWARM", "0")
    monkeypatch.setattr(app_mod, "_run_clap_prewarm", lambda: called.__setitem__("n", called["n"] + 1))

    app_mod._maybe_start_clap_prewarm()
    assert called["n"] == 0


def test_prewarm_sync_runs_inline(monkeypatch):
    called = {"n": 0}
    monkeypatch.setenv("LYRA_CLAP_PREWARM", "1")
    monkeypatch.setenv("LYRA_CLAP_PREWARM_MODE", "sync")
    monkeypatch.setattr(app_mod, "_run_clap_prewarm", lambda: called.__setitem__("n", called["n"] + 1))

    app_mod._maybe_start_clap_prewarm()
    assert called["n"] == 1


def test_prewarm_background_starts_thread(monkeypatch):
    state = {"started": False}

    class _FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target

        def start(self):
            state["started"] = True

    monkeypatch.setenv("LYRA_CLAP_PREWARM", "1")
    monkeypatch.setenv("LYRA_CLAP_PREWARM_MODE", "background")
    monkeypatch.setattr(app_mod.threading, "Thread", _FakeThread)
    monkeypatch.setattr(app_mod, "_run_clap_prewarm", lambda: None)

    app_mod._maybe_start_clap_prewarm()
    assert state["started"] is True
