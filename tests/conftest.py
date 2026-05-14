"""Test fixtures — isolate the SQLite DB and memory dir per test."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_workdir(monkeypatch):
    """Run each test inside a fresh tempdir so accounts.db / memory/ never leak."""
    with tempfile.TemporaryDirectory(prefix="tf-tests-") as tmp:
        # Code under test uses cwd-relative paths for accounts.db and ./memory/.
        monkeypatch.chdir(tmp)
        Path(tmp, "memory").mkdir(exist_ok=True)
        yield Path(tmp)
