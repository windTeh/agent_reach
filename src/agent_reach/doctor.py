"""Non-destructive diagnostics for project-local channels."""

from __future__ import annotations

from .backends.registry import resolve_active_backend
from .channels.opencli import OpenCLIChannel
from .config import load_config
from .models import DoctorReport, HealthStatus
from .output import worst_status
from .paths import RuntimePaths


def build_doctor_report(paths: RuntimePaths) -> DoctorReport:
    """Build a report without creating runtime directories or contacting browsers."""
    config = load_config(paths)
    channels = [OpenCLIChannel(paths).inspect()]
    active_backend, backends = resolve_active_backend([], config)
    status = worst_status([active_backend.status, *(channel.status for channel in channels)])
    return DoctorReport(
        schema_version=1,
        status=status,
        project_root=str(paths.project_root),
        runtime_root=str(paths.runtime_root),
        active_backend=active_backend,
        channels=channels,
        backends=backends,
    )
