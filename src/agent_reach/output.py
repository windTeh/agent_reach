"""Terminal rendering with strict JSON stdout support."""

from __future__ import annotations

import json
from typing import TextIO

from .models import DoctorReport, HealthStatus


def dump_json(value: object, stream: TextIO) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), file=stream)


def render_doctor_text(report: DoctorReport, stream: TextIO) -> None:
    print(f"Agent Reach 诊断：{report.status.value}", file=stream)
    print(f"项目目录：{report.project_root}", file=stream)
    print(f"运行时目录：{report.runtime_root}", file=stream)
    active = report.active_backend
    print(f"当前后端：{active.id or '未配置'}（{active.status.value}；{active.source}）", file=stream)
    print(f"说明：{active.message}", file=stream)
    print("\n频道：", file=stream)
    for channel in report.channels:
        print(f"  [{channel.status.value}] {channel.id}", file=stream)
        for check in channel.checks:
            print(f"    [{check.status.value}] {check.message}", file=stream)
            if check.fix:
                for instruction in check.fix.instructions:
                    print(f"      修复：{instruction}", file=stream)
    if report.backends:
        print("\n后端：", file=stream)
        for backend in report.backends:
            current = "（当前）" if backend.active else ""
            print(f"  [{backend.status.value}] {backend.id}{current}：{backend.message}", file=stream)


def worst_status(statuses: list[HealthStatus]) -> HealthStatus:
    priority = {
        HealthStatus.ERROR: 5,
        HealthStatus.MANUAL_ACTION_REQUIRED: 4,
        HealthStatus.WARNING: 3,
        HealthStatus.SKIPPED: 2,
        HealthStatus.OK: 1,
    }
    return max(statuses or [HealthStatus.OK], key=priority.__getitem__)
