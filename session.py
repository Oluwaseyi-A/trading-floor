"""Session helpers — id generation, memory-file path, and cleanup."""

import os
import shutil
import time
import uuid
from pathlib import Path

from database import cleanup_session as _db_cleanup_session

MEMORY_DIR = Path("./memory")
MEMORY_TTL_SECONDS = 24 * 60 * 60  # 24h belt-and-braces TTL on memory files


def new_session_id() -> str:
    """Generate a per-visitor session id (32 hex chars)."""
    return uuid.uuid4().hex


def memory_file_for(session_id: str, trader_name: str) -> Path:
    return MEMORY_DIR / f"{session_id}_{trader_name.lower()}.db"


def cleanup_session(session_id: str) -> None:
    """Wipe a session's DB rows and memory files. Safe to call multiple times."""
    _db_cleanup_session(session_id)

    if not MEMORY_DIR.exists():
        return
    prefix = f"{session_id}_"
    for path in MEMORY_DIR.iterdir():
        if path.name.startswith(prefix):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                else:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


def janitor_sweep(ttl_seconds: int = MEMORY_TTL_SECONDS) -> int:
    """Delete memory files untouched in the last ttl_seconds. Returns count removed."""
    if not MEMORY_DIR.exists():
        return 0

    cutoff = time.time() - ttl_seconds
    removed = 0
    for path in MEMORY_DIR.iterdir():
        if path.name.startswith(".") or not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def ensure_memory_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


# Public-app guardrails — read once at import time; CLI ignores these.
def session_caps() -> tuple[int, int]:
    """Returns (max_runs_per_session, session_max_seconds). 0 == unlimited."""
    max_runs = int(os.getenv("MAX_RUNS_PER_SESSION", "0"))
    max_minutes = int(os.getenv("SESSION_MAX_MINUTES", "0"))
    return max_runs, max_minutes * 60
