"""Shared constants for Agent Reach."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "agent-reach"
PROJECT_MARKER = "pyproject.toml"
RUNTIME_DIRNAME = "runtime"
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/Panniantong/agent-reach/main/pyproject.toml"
DEFAULT_UPDATE_HOSTS = frozenset({"raw.githubusercontent.com"})
DEFAULT_NETWORK_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_DOWNLOAD_BYTES = 1_000_000
MANAGED_SKILL_NAME = "agent-reach"
MANAGED_SKILL_MARKER = ".agent-reach-managed.json"

EXIT_OK = 0
EXIT_UNHEALTHY = 1
EXIT_USAGE = 2
EXIT_OPERATION_FAILED = 3
EXIT_NETWORK_UNAVAILABLE = 4

RUNTIME_DIRECTORIES = (
    "config",
    "state",
    "cache",
    "tmp",
    "logs",
    "tools",
    "home",
)

DEFAULT_CONFIG = """# Agent Reach project-local configuration\n# Choose a configured backend by its id, or leave blank.\nactive_backend = \"\"\n\n[backends]\n# Example:\n# [backends.opencli]\n# enabled = true\n"""

DEFAULT_SKILL = """---\nname: agent-reach\ndescription: Inspect and maintain Agent Reach project-local channels.\n---\n\n# Agent Reach\n\nUse `agent-reach doctor` to inspect project-local channel health. Browser extension\ninstallation and authentication are always manual user actions.\n"""


def project_tool_path(project_root: Path) -> Path:
    """Return the only supported location for project-managed executable tools."""
    return project_root / "tools" / "bin"
