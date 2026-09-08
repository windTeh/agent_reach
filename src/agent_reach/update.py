"""Safe update availability checking; this module never installs packages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from packaging.version import InvalidVersion, Version

from . import __version__
from .constants import DEFAULT_UPDATE_URL
from .errors import NetworkError
from .network import fetch_official_text, parse_pyproject_version
from .paths import RuntimePaths, ensure_within_project


@dataclass(frozen=True)
class UpdateResult:
    current_version: str
    available_version: str | None
    update_available: bool | None
    source: str
    checked_at: str | None
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _cache_path(paths: RuntimePaths) -> Path:
    return paths.state_dir / "update-check.json"


def _read_cache(paths: RuntimePaths) -> UpdateResult | None:
    target = _cache_path(paths)
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return UpdateResult(**payload)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _write_cache(paths: RuntimePaths, result: UpdateResult) -> None:
    paths.ensure_directories()
    target = ensure_within_project(_cache_path(paths), paths.project_root)
    temporary = ensure_within_project(target.with_suffix(".tmp"), paths.project_root)
    temporary.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def check_for_updates(paths: RuntimePaths, *, offline: bool = False) -> UpdateResult:
    """Compare the installed version with official metadata, never downloading a package."""
    if offline:
        cached = _read_cache(paths)
        if cached:
            return UpdateResult(
                current_version=__version__,
                available_version=cached.available_version,
                update_available=cached.update_available,
                source="项目内缓存（离线）",
                checked_at=cached.checked_at,
                message="离线模式：使用项目内缓存，未发起网络请求。",
            )
        return UpdateResult(__version__, None, None, "离线", None, "离线模式且没有项目内更新缓存。")

    response = fetch_official_text(DEFAULT_UPDATE_URL)
    available = parse_pyproject_version(response.text)
    try:
        update_available = Version(available) > Version(__version__)
    except InvalidVersion as error:
        raise NetworkError("本地或远程版本不符合 PEP 440。") from error
    result = UpdateResult(
        current_version=__version__,
        available_version=available,
        update_available=update_available,
        source=response.url,
        checked_at=datetime.now(timezone.utc).isoformat(),
        message="发现可用更新。" if update_available else "当前版本已是最新或不低于远程版本。",
    )
    _write_cache(paths, result)
    return result
