from __future__ import annotations

from agent_reach.backends.registry import resolve_active_backend
from agent_reach.models import BackendReport, HealthStatus


def test_only_healthy_backend_is_inferred():
    report = BackendReport("local", HealthStatus.OK, True, True, message="ready")
    active, reports = resolve_active_backend([report], {})
    assert active.id == "local"
    assert active.source == "自动推断"
    assert reports[0].active


def test_invalid_explicit_backend_fails():
    active, _ = resolve_active_backend([], {"active_backend": "missing"})
    assert active.id == "missing"
    assert active.status == HealthStatus.ERROR
