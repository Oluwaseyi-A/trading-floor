"""Tests for the SESSION_MAX_MINUTES / MAX_RUNS_PER_SESSION guardrails."""

import importlib
import time


def _reload():
    import session
    import session_state
    importlib.reload(session)
    importlib.reload(session_state)
    return session, session_state


def test_caps_unset_means_unlimited(monkeypatch):
    # Set to "0" — session.session_caps() treats <=0 as "no cap". (Reloading
    # the module via _reload runs load_dotenv which would re-import whatever
    # .env says, so delenv alone wouldn't be enough.)
    monkeypatch.setenv("MAX_RUNS_PER_SESSION", "0")
    monkeypatch.setenv("SESSION_MAX_MINUTES", "0")
    session, session_state = _reload()
    state = session_state.upsert_state("s1")
    state.traders = ["dummy"]
    state.started_at = time.time()
    assert session_state.remaining_runs(state) == -1
    assert session_state.remaining_seconds(state) == -1
    ok, _ = session_state.can_run(state)
    assert ok


def test_max_runs_blocks_after_cap(monkeypatch):
    monkeypatch.setenv("MAX_RUNS_PER_SESSION", "2")
    monkeypatch.setenv("SESSION_MAX_MINUTES", "0")
    session, session_state = _reload()
    state = session_state.upsert_state("s2")
    state.traders = ["dummy"]
    state.started_at = time.time()
    state.runs_completed = 2
    ok, reason = session_state.can_run(state)
    assert not ok
    assert "run cap" in reason.lower()


def test_max_time_blocks_after_window(monkeypatch):
    monkeypatch.setenv("MAX_RUNS_PER_SESSION", "0")
    monkeypatch.setenv("SESSION_MAX_MINUTES", "10")
    session, session_state = _reload()
    state = session_state.upsert_state("s3")
    state.traders = ["dummy"]
    # 11 minutes ago — past the 10-minute window.
    state.started_at = time.time() - 11 * 60
    ok, reason = session_state.can_run(state)
    assert not ok
    assert "time cap" in reason.lower()


def test_is_running_blocks(monkeypatch):
    monkeypatch.delenv("MAX_RUNS_PER_SESSION", raising=False)
    monkeypatch.delenv("SESSION_MAX_MINUTES", raising=False)
    session, session_state = _reload()
    state = session_state.upsert_state("s4")
    state.traders = ["dummy"]
    state.is_running = True
    ok, reason = session_state.can_run(state)
    assert not ok
    assert "in progress" in reason
