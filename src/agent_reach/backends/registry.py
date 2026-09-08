"""Deterministic active-backend resolution."""

from __future__ import annotations

import os
from typing import Iterable

from ..models import ActiveBackend, BackendReport, HealthStatus


def resolve_active_backend(
    reports: Iterable[BackendReport], config: dict[str, object], override: str | None = None
) -> tuple[ActiveBackend, list[BackendReport]]:
    """Select an active backend without choosing arbitrarily."""
    items = list(reports)
    configured = str(config.get("active_backend", "")).strip()
    requested = (override or os.environ.get("AGENT_REACH_ACTIVE_BACKEND") or configured).strip()
    source = "命令行" if override else "环境变量" if os.environ.get("AGENT_REACH_ACTIVE_BACKEND") else "项目配置"

    if requested:
        matching = next((item for item in items if item.id == requested), None)
        if matching and matching.available:
            marked = [_mark_active(item, item.id == requested) for item in items]
            return (
                ActiveBackend(requested, HealthStatus.OK, source, "已按显式配置选择后端。"),
                marked,
            )
        return (
            ActiveBackend(requested, HealthStatus.ERROR, source, "指定的当前后端不存在或不可用。"),
            items,
        )

    healthy = [item for item in items if item.available and item.status == HealthStatus.OK]
    if len(healthy) == 1:
        selected = healthy[0]
        marked = [_mark_active(item, item.id == selected.id) for item in items]
        return (
            ActiveBackend(selected.id, HealthStatus.OK, "自动推断", "仅发现一个健康后端，已自动选择。"),
            marked,
        )
    if not items:
        return (
            ActiveBackend(None, HealthStatus.ERROR, "未配置", "尚未注册可用后端。"),
            [],
        )
    return (
        ActiveBackend(None, HealthStatus.ERROR, "未配置", "存在多个或没有健康后端；请在 runtime/config/config.toml 设置 active_backend。"),
        items,
    )


def _mark_active(report: BackendReport, active: bool) -> BackendReport:
    return BackendReport(
        id=report.id,
        status=report.status,
        configured=report.configured,
        available=report.available,
        active=active,
        message=report.message,
    )
