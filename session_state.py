"""Per-session runtime state for the hosted Gradio app.

Keyed by `gr.Request.session_hash`. Holds the configured persona slots, the
Trader instances built from them, the run counter, and the wall-clock start
time used by the public-app guardrails. Module-level dict + a lock — Gradio
hands the same session_hash to every callback for a given browser tab, so
this is the natural place to keep mutable per-visitor state.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from traders import Trader
from personas import PersonaSlot
from session import session_caps


@dataclass
class RoundState:
    session_id: str
    slots: list[PersonaSlot] = field(default_factory=list)
    initial_balance: float = 20_000.0
    traders: list[Trader] = field(default_factory=list)
    runs_completed: int = 0
    started_at: float | None = None
    auto_run_enabled: bool = False
    auto_run_interval_min: int = 5
    is_running: bool = False  # set while a round is actively executing
    last_error: str | None = None


_SESSIONS: dict[str, RoundState] = {}
_LOCK = threading.Lock()


def get_state(session_id: str) -> RoundState | None:
    with _LOCK:
        return _SESSIONS.get(session_id)


def upsert_state(session_id: str) -> RoundState:
    with _LOCK:
        state = _SESSIONS.get(session_id)
        if state is None:
            state = RoundState(session_id=session_id)
            _SESSIONS[session_id] = state
        return state


def drop_state(session_id: str) -> None:
    with _LOCK:
        _SESSIONS.pop(session_id, None)


def remaining_runs(state: RoundState) -> int:
    """Runs left under MAX_RUNS_PER_SESSION. -1 means unlimited."""
    max_runs, _ = session_caps()
    if max_runs <= 0:
        return -1
    return max(0, max_runs - state.runs_completed)


def remaining_seconds(state: RoundState) -> int:
    """Seconds left under SESSION_MAX_MINUTES. -1 means unlimited."""
    _, max_seconds = session_caps()
    if max_seconds <= 0:
        return -1
    if state.started_at is None:
        return max_seconds
    elapsed = int(time.time() - state.started_at)
    return max(0, max_seconds - elapsed)


def can_run(state: RoundState) -> tuple[bool, str]:
    """(allowed, reason). reason is empty if allowed."""
    if state.is_running:
        return False, "A trading round is already in progress."
    if not state.traders:
        return False, "Click Launch trading floor first."

    runs_left = remaining_runs(state)
    if runs_left == 0:
        return False, "Session run cap reached (MAX_RUNS_PER_SESSION)."

    secs_left = remaining_seconds(state)
    if secs_left == 0:
        return False, "Session time cap reached (SESSION_MAX_MINUTES)."

    return True, ""
