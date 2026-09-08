"""Small, project-local configuration reader."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.7-3.10
    import tomli as tomllib
from pathlib import Path
from typing import Any

from .constants import DEFAULT_CONFIG
from .errors import ConfigurationError
from .paths import RuntimePaths, ensure_within_project


def config_path(paths: RuntimePaths) -> Path:
    return paths.config_dir / "config.toml"


def ensure_default_config(paths: RuntimePaths) -> Path:
    """Create only the project-local template when a mutating command requests it."""
    paths.ensure_directories()
    target = ensure_within_project(config_path(paths), paths.project_root)
    if not target.exists():
        target.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return target


def load_config(paths: RuntimePaths) -> dict[str, Any]:
    """Read configuration without creating any files."""
    target = config_path(paths)
    if not target.exists():
        return {}
    try:
        with target.open("rb") as handle:
            loaded = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"无法读取项目配置 {target}: {error}") from error
    if not isinstance(loaded, dict):
        raise ConfigurationError("项目配置必须是 TOML 对象。")
    return loaded
