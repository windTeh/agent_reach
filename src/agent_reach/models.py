"""Serializable domain models used by diagnostics and maintenance commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"
    MANUAL_ACTION_REQUIRED = "manual_action_required"


@dataclass(frozen=True)
class FixAction:
    kind: str
    instructions: list[str]


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: HealthStatus
    message: str
    fix: FixAction | None = None


@dataclass(frozen=True)
class ChannelReport:
    id: str
    status: HealthStatus
    checks: list[CheckResult]


@dataclass(frozen=True)
class BackendReport:
    id: str
    status: HealthStatus
    configured: bool
    available: bool
    active: bool = False
    message: str = ""


@dataclass(frozen=True)
class ActiveBackend:
    id: str | None
    status: HealthStatus
    source: str
    message: str


@dataclass(frozen=True)
class DoctorReport:
    schema_version: int
    status: HealthStatus
    project_root: str
    runtime_root: str
    active_backend: ActiveBackend
    channels: list[ChannelReport] = field(default_factory=list)
    backends: list[BackendReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
