"""Project-local paths and boundary enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .constants import PROJECT_MARKER, RUNTIME_DIRECTORIES, RUNTIME_DIRNAME
from .errors import PathBoundaryError


@dataclass(frozen=True)
class RuntimePaths:
    """All writable Agent Reach locations, constrained to one project."""

    project_root: Path
    runtime_root: Path
    config_dir: Path
    state_dir: Path
    cache_dir: Path
    temp_dir: Path
    logs_dir: Path
    tools_dir: Path
    home_dir: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "RuntimePaths":
        root = project_root.resolve()
        runtime = root / RUNTIME_DIRNAME
        return cls(
            project_root=root,
            runtime_root=runtime,
            config_dir=runtime / "config",
            state_dir=runtime / "state",
            cache_dir=runtime / "cache",
            temp_dir=runtime / "tmp",
            logs_dir=runtime / "logs",
            tools_dir=runtime / "tools",
            home_dir=runtime / "home",
        )

    def all_directories(self) -> tuple[Path, ...]:
        return (
            self.runtime_root,
            self.config_dir,
            self.state_dir,
            self.cache_dir,
            self.temp_dir,
            self.logs_dir,
            self.tools_dir,
            self.home_dir,
        )

    def ensure_directories(self) -> None:
        for directory in self.all_directories():
            ensure_within_project(directory, self.project_root)
            directory.mkdir(parents=True, exist_ok=True)

    def child_environment(self, inherited: dict[str, str] | None = None) -> dict[str, str]:
        """Return an environment that redirects conventional writable homes locally."""
        environment = dict(os.environ if inherited is None else inherited)
        home = str(self.home_dir)
        environment.update(
            {
                "HOME": home,
                "USERPROFILE": home,
                "XDG_CONFIG_HOME": str(self.config_dir),
                "XDG_CACHE_HOME": str(self.cache_dir),
                "XDG_STATE_HOME": str(self.state_dir),
                "TMP": str(self.temp_dir),
                "TEMP": str(self.temp_dir),
                "TMPDIR": str(self.temp_dir),
                "AGENT_REACH_PROJECT_ROOT": str(self.project_root),
            }
        )
        return environment


def locate_project_root(start: Path | None = None) -> Path:
    """Find the project marker without falling back to a user-home directory."""
    explicit = os.environ.get("AGENT_REACH_PROJECT_ROOT")
    candidates = [Path(explicit)] if explicit else []
    candidates.append(Path.cwd() if start is None else start)

    for candidate in candidates:
        candidate = candidate.resolve()
        for parent in (candidate, *candidate.parents):
            marker = parent / PROJECT_MARKER
            if marker.is_file():
                return parent

    package_root = Path(__file__).resolve().parents[2]
    if (package_root / PROJECT_MARKER).is_file():
        return package_root
    raise PathBoundaryError(
        "无法定位 Agent Reach 项目根目录；请在包含 pyproject.toml 的项目目录中运行，"
        "或设置 AGENT_REACH_PROJECT_ROOT。"
    )


def ensure_within_project(path: Path, project_root: Path) -> Path:
    """Resolve *path* and reject any location outside the project tree."""
    root = project_root.resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PathBoundaryError(f"拒绝写入项目外路径：{resolved}") from error
    return resolved


def default_paths(start: Path | None = None) -> RuntimePaths:
    """Locate the project and return its isolated runtime layout."""
    return RuntimePaths.from_project_root(locate_project_root(start))
