"""Command-line interface for Agent Reach."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from .constants import EXIT_NETWORK_UNAVAILABLE, EXIT_OK, EXIT_UNHEALTHY, EXIT_USAGE
from .doctor import build_doctor_report
from .errors import AgentReachError, NetworkError
from .installer import install_opencli
from .output import dump_json, render_doctor_text
from .paths import default_paths
from .skill import install_managed_skill
from .update import check_for_updates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-reach", description="项目内隔离的 Agent Reach CLI")
    parser.add_argument("--version", action="version", version=f"agent-reach {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="显示当前版本")

    doctor = subparsers.add_parser("doctor", help="检查频道与后端状态")
    doctor.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")
    doctor.add_argument("--offline", action="store_true", help="兼容选项；当前诊断不访问网络")

    update = subparsers.add_parser("check-update", help="只检查可用更新，不执行升级")
    update.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")
    update.add_argument("--offline", action="store_true", help="仅读取项目内缓存")

    install = subparsers.add_parser("install", help="维护项目托管渠道工具")
    install.add_argument("--system", action="store_true", help="兼容参数；映射为 project-managed 模式")
    install.add_argument("--channels", required=True, help="逗号分隔的频道列表；第一期仅支持 opencli")
    install.add_argument("--dry-run", action="store_true", help="只显示计划，不修改文件")
    install.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")

    skill = subparsers.add_parser("skill", help="管理项目内受管理 skill")
    skill.add_argument("--install", action="store_true", help="安装或刷新 Agent Reach skill")
    skill.add_argument("--dry-run", action="store_true", help="只显示计划，不修改文件")
    skill.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")
    return parser


def _configure_utf8_streams() -> None:
    """Keep Chinese text and JSON stable in legacy Windows consoles when possible."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_streams()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "version":
        print(f"agent-reach {__version__}")
        return EXIT_OK
    if not arguments.command:
        parser.print_help()
        return EXIT_USAGE

    try:
        paths = default_paths()
        if arguments.command == "doctor":
            report = build_doctor_report(paths)
            if arguments.as_json:
                dump_json(report.to_dict(), sys.stdout)
            else:
                render_doctor_text(report, sys.stdout)
            return EXIT_OK

        if arguments.command == "check-update":
            result = check_for_updates(paths, offline=arguments.offline)
            if arguments.as_json:
                dump_json(result.to_dict(), sys.stdout)
            else:
                print(f"当前版本：{result.current_version}")
                print(f"可用版本：{result.available_version or '未知'}")
                print(f"来源：{result.source}")
                print(result.message)
            return EXIT_OK

        if arguments.command == "install":
            channels = {item.strip() for item in arguments.channels.split(",") if item.strip()}
            if channels != {"opencli"}:
                parser.error("第一期仅支持 --channels opencli")
            result = install_opencli(paths, system=arguments.system, dry_run=arguments.dry_run)
            if arguments.as_json:
                dump_json(result.to_dict(), sys.stdout)
            else:
                print(result.message)
                print(f"项目目标：{result.target}")
                for action in result.actions:
                    print(f"- {action}")
            return EXIT_OK if result.status in {"planned", "ok"} else EXIT_UNHEALTHY

        if arguments.command == "skill":
            if not arguments.install:
                parser.error("当前仅支持 skill --install")
            result = install_managed_skill(paths, dry_run=arguments.dry_run)
            if arguments.as_json:
                dump_json(result.to_dict(), sys.stdout)
            else:
                print(result.message)
                print(f"项目目标：{result.target}")
            return EXIT_OK if result.status in {"planned", "ok"} else EXIT_UNHEALTHY
    except NetworkError as error:
        print(f"网络检查失败：{error}", file=sys.stderr)
        return EXIT_NETWORK_UNAVAILABLE
    except AgentReachError as error:
        print(f"操作失败：{error}", file=sys.stderr)
        return EXIT_UNHEALTHY
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
