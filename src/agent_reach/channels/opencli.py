"""Read-only OpenCLI diagnostics.

This adapter deliberately never inspects browser profiles, cookies, or credential stores.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ChannelReport, CheckResult, FixAction, HealthStatus
from ..paths import RuntimePaths, ensure_within_project


class OpenCLIChannel:
    """Inspect the project-managed OpenCLI wrapper and required manual steps."""

    id = "opencli"

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths

    @property
    def executable_candidates(self) -> tuple[Path, ...]:
        tool_bin = self.paths.project_root / "tools" / "bin"
        return (tool_bin / "opencli.cmd", tool_bin / "opencli.exe", tool_bin / "opencli")

    def inspect(self) -> ChannelReport:
        executable = next((item for item in self.executable_candidates if item.is_file()), None)
        checks: list[CheckResult] = []
        if executable:
            checks.append(
                CheckResult(
                    id="project_managed_cli",
                    status=HealthStatus.OK,
                    message=f"检测到项目托管的 OpenCLI：{executable}",
                )
            )
        else:
            checks.append(
                CheckResult(
                    id="project_managed_cli",
                    status=HealthStatus.ERROR,
                    message="未检测到项目托管的 OpenCLI。",
                    fix=FixAction(
                        kind="command",
                        instructions=[
                            "先由你自行将 OpenCLI 安装到本项目 tools/bin/，不要安装到全局环境。",
                            "安装完成后执行：agent-reach install --system --channels opencli --dry-run",
                        ],
                    ),
                )
            )

        checks.append(
            CheckResult(
                id="browser_extension",
                status=HealthStatus.MANUAL_ACTION_REQUIRED,
                message="OpenCLI 浏览器扩展状态无法由 Agent Reach 自动验证。",
                fix=FixAction(
                    kind="manual",
                    instructions=[
                        "请在浏览器扩展商店中自行安装或启用 OpenCLI 扩展。",
                        "不要授予 Agent Reach 读取浏览器 Cookie 或 profile 的权限。",
                    ],
                ),
            )
        )
        checks.append(
            CheckResult(
                id="browser_login",
                status=HealthStatus.MANUAL_ACTION_REQUIRED,
                message="OpenCLI 登录状态需要由你在浏览器中自行确认。",
                fix=FixAction(
                    kind="manual",
                    instructions=[
                        "在浏览器中自行完成 OpenCLI 登录（如需要）。",
                        "完成后执行：agent-reach doctor",
                    ],
                ),
            )
        )

        status = HealthStatus.OK if executable else HealthStatus.ERROR
        if status == HealthStatus.OK:
            status = HealthStatus.MANUAL_ACTION_REQUIRED
        return ChannelReport(id=self.id, status=status, checks=checks)
