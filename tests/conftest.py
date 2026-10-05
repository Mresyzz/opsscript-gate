from __future__ import annotations

import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_ci_environment(monkeypatch, tmp_path):
    """
    Isolate CI workflow environment variables during test runs.
    Prevents tests invoking CLI entry points from polluting the host runner's
    GITHUB_STEP_SUMMARY file or printing workflow commands to stdout.
    """
    test_summary_file = tmp_path / "ci_step_summary_isolation.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(test_summary_file))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
