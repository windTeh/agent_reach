from __future__ import annotations

from pathlib import Path

import pytest

from agent_reach.errors import PathBoundaryError
from agent_reach.paths import ensure_within_project


def test_runtime_paths_remain_inside_project(paths):
    paths.ensure_directories()
    assert all(str(path.resolve()).startswith(str(paths.project_root)) for path in paths.all_directories())


def test_child_environment_is_project_local(paths):
    environment = paths.child_environment({"PATH": "safe"})
    assert environment["HOME"] == str(paths.home_dir)
    assert environment["USERPROFILE"] == str(paths.home_dir)
    assert environment["TMP"] == str(paths.temp_dir)
    assert environment["TEMP"] == str(paths.temp_dir)
    assert environment["PATH"] == "safe"


def test_rejects_path_outside_project(project_root: Path, tmp_path: Path):
    with pytest.raises(PathBoundaryError):
        ensure_within_project(tmp_path.parent / "outside.txt", project_root)
