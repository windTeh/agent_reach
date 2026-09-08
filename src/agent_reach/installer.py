"""Project-managed maintenance operations.

The first release intentionally does not install unregistered tools. It only describes
what a future verified updater would do inside this project.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .constants import project_tool_path
from .paths import RuntimePaths, ensure_within_project


@dataclass(frozen=True)
class InstallResult:
    channel: str
    status: str
    dry_run: bool
    target: str
    message: str
    actions: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _manifest_path(paths: RuntimePaths) -> Path:
    return paths.project_root / "tools" / "manifests" / "managed-tools.json"


def _managed_opencli(paths: RuntimePaths) -> bool:
    target = _manifest_path(paths)
    if not target.is_file():
        return False
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("opencli"))


def install_opencli(paths: RuntimePaths, *, system: bool, dry_run: bool) -> InstallResult:
    """Describe safe, project-only OpenCLI maintenance without global installation."""
    target = ensure_within_project(project_tool_path(paths.project_root), paths.project_root)
    prefix = "已将 --system 映射为项目托管模式。" if system else "使用项目托管模式。"
    if not _managed_opencli(paths):
        return InstallResult(
            channel="opencli",
            status="manual_action_required",
            dry_run=dry_run,
            target=str(target),
            message=f"{prefix} OpenCLI 尚未在本项目的受管理清单中登记，因此不会自动安装。",
            actions=[
                f"请自行将 OpenCLI 安装到：{target}",
                "将受管理安装信息写入 tools/manifests/managed-tools.json 后，再运行此命令以检查可升级状态。",
                "不要使用全局 npm、pip、pipx 或修改 PATH。",
                "浏览器扩展安装与登录必须在浏览器中手动完成。",
            ],
        )
    return InstallResult(
        channel="opencli",
        status="not_implemented",
        dry_run=dry_run,
        target=str(target),
        message=f"{prefix} 已检测到受管理 OpenCLI，但安全更新器尚未配置官方可验证的分发清单。",
        actions=[
            "未执行下载、覆盖、卸载或系统级安装。",
            "请先核验 OpenCLI 的官方分发 URL、版本元数据和校验和策略，再启用实际更新。",
        ],
    )
