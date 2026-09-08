"""Project-local managed skill installation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .constants import DEFAULT_SKILL, MANAGED_SKILL_MARKER, MANAGED_SKILL_NAME
from .paths import RuntimePaths, ensure_within_project


@dataclass(frozen=True)
class SkillResult:
    status: str
    dry_run: bool
    target: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def install_managed_skill(paths: RuntimePaths, *, dry_run: bool) -> SkillResult:
    """Install only this project's managed skill and preserve unrelated skills."""
    target = ensure_within_project(paths.project_root / "tools" / "skills" / MANAGED_SKILL_NAME, paths.project_root)
    marker = target / MANAGED_SKILL_MARKER
    skill_file = target / "SKILL.md"
    if dry_run:
        return SkillResult("planned", True, str(target), "演练模式：不会写入 skill 文件。")

    target.mkdir(parents=True, exist_ok=True)
    if skill_file.exists() and not marker.exists():
        return SkillResult(
            "manual_action_required",
            False,
            str(target),
            "目标目录包含未由 Agent Reach 管理的 SKILL.md；为保护用户内容，未覆盖它。",
        )
    skill_file.write_text(DEFAULT_SKILL, encoding="utf-8")
    marker.write_text(json.dumps({"managed_by": "agent-reach", "schema_version": 1}), encoding="utf-8")
    return SkillResult("ok", False, str(target), "已在项目内安装或刷新 Agent Reach 受管理 skill。")
