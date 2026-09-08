from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_reach.paths import RuntimePaths


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "agent-reach"\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_REACH_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def paths(project_root: Path) -> RuntimePaths:
    return RuntimePaths.from_project_root(project_root)
